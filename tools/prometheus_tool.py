import asyncio
import aiohttp
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import urllib.parse

from .base_tool import BaseTool, ToolMetadata, ToolResult


class PrometheusQueryTool(BaseTool):
    """Tool for querying metrics from Prometheus."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Prometheus query tool."""
        self.config = config or {}
        self.base_url = self.config.get("prometheus_url", "http://localhost:9090")
        self.auth_headers = self._build_auth_headers()
        super().__init__(config)
    
    @property
    def metadata(self) -> ToolMetadata:
        """Return metadata for Prometheus query tool."""
        return ToolMetadata(
            id="prometheus_query",
            name="Prometheus Query",
            description="Query metrics from Prometheus using PromQL. Supports instant and range queries. Optional parameters: query_type (default: instant), start_time, end_time, step (default: 15s), timeout.",
            inputs={
                "query": "string - PromQL query string (e.g., 'up', 'rate(http_requests_total[5m])')"
            },
            category="metrics"
        )
    
    def _validate_config(self) -> None:
        """Validate Prometheus tool configuration."""
        if not self.base_url:
            raise RuntimeError("Prometheus URL must be configured")
        
        # Optional: Test connectivity
        try:
            import requests
            response = requests.get(f"{self.base_url}/-/healthy", timeout=5)
            if response.status_code != 200:
                raise RuntimeError(f"Prometheus not healthy: {response.status_code}")
        except Exception as e:
            # Don't fail validation for connectivity issues
            pass
    
    def _build_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers for Prometheus requests."""
        headers = {"Content-Type": "application/json"}
        
        # Basic auth support
        username = self.config.get("username")
        password = self.config.get("password")
        if username and password:
            import base64
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
        
        # Bearer token support
        token = self.config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        return headers
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute Prometheus query."""
        try:
            self.validate_inputs(inputs)
            
            query = inputs["query"]
            query_type = inputs.get("query_type", "instant")
            start_time = inputs.get("start_time")
            end_time = inputs.get("end_time")
            step = inputs.get("step", "15s")
            timeout = inputs.get("timeout")
            
            # Build query parameters
            params = {"query": query}
            
            if timeout:
                params["timeout"] = timeout
            
            if query_type == "range":
                endpoint = "/api/v1/query_range"
                end_ts = self._parse_time(end_time) if end_time else datetime.now()
                start_ts = self._parse_time(start_time) if start_time else end_ts - timedelta(hours=1)
                
                params.update({
                    "start": start_ts.timestamp(),
                    "end": end_ts.timestamp(),
                    "step": step
                })
            else:
                endpoint = "/api/v1/query"
                # For instant queries, only set time if it's significantly in the past
                # Otherwise get latest data by omitting time parameter
                if end_time:
                    end_ts = self._parse_time(end_time)
                    now = datetime.now()
                    # Only set time if it's more than 5 minutes ago (historical query)
                    if (now - end_ts).total_seconds() > 300:
                        params["time"] = end_ts.timestamp()
            
            url = f"{self.base_url}{endpoint}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self.auth_headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        return ToolResult(
                            success=False,
                            data=None,
                            error_message=f"Prometheus query failed: HTTP {response.status} - {error_text}"
                        )
                    
                    response_data = await response.json()
                    
                    if response_data.get("status") != "success":
                        return ToolResult(
                            success=False,
                            data=None,
                            error_message=f"Prometheus query failed: {response_data.get('error', 'Unknown error')}"
                        )
                    
                    # Parse Prometheus response
                    parsed_metrics = self._parse_prometheus_response(response_data["data"])
                    
                    return ToolResult(
                        success=True,
                        data={
                            "query": query,
                            "query_type": query_type,
                            "result_type": response_data["data"]["resultType"],
                            "metrics": parsed_metrics,
                            "execution_time": response_data.get("data", {}).get("stats", {}).get("timings", {}).get("evalTotalTime")
                        },
                        metadata={
                            "query_time": datetime.now().isoformat(),
                            "prometheus_url": url,
                            "query_params": params
                        }
                    )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Prometheus query execution failed: {str(e)}"
            )
    
    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string to datetime object."""
        if not time_str:
            return datetime.now()
        
        # Handle relative times like "1h", "30m", "2d"
        if time_str.endswith(('h', 'm', 'd', 's')):
            unit = time_str[-1]
            value = int(time_str[:-1])
            
            if unit == 's':
                delta = timedelta(seconds=value)
            elif unit == 'm':
                delta = timedelta(minutes=value)
            elif unit == 'h':
                delta = timedelta(hours=value)
            elif unit == 'd':
                delta = timedelta(days=value)
            else:
                raise ValueError(f"Unknown time unit: {unit}")
            
            return datetime.now() - delta
        
        # Handle ISO format
        try:
            return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except ValueError:
            # Try common timestamp formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S']:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue
            
            raise ValueError(f"Unable to parse time string: {time_str}")
    
    def _parse_prometheus_response(self, data: dict) -> List[dict]:
        """Parse Prometheus API response into structured format."""
        result_type = data.get("resultType")
        result = data.get("result", [])
        
        parsed_metrics = []
        
        for metric in result:
            metric_labels = metric.get("metric", {})
            
            if result_type == "vector":
                # Instant query result
                timestamp, value = metric.get("value", [None, None])
                if timestamp and value:
                    parsed_metrics.append({
                        "labels": metric_labels,
                        "timestamp": datetime.fromtimestamp(float(timestamp)).isoformat(),
                        "value": float(value)
                    })
            
            elif result_type == "matrix":
                # Range query result
                values = metric.get("values", [])
                parsed_values = []
                
                for timestamp, value in values:
                    parsed_values.append({
                        "timestamp": datetime.fromtimestamp(float(timestamp)).isoformat(),
                        "value": float(value)
                    })
                
                parsed_metrics.append({
                    "labels": metric_labels,
                    "values": parsed_values
                })
        
        return parsed_metrics


class PrometheusAlertsTool(BaseTool):
    """Tool for querying alerts from Prometheus Alertmanager."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.base_url = self.config.get("prometheus_url", "http://localhost:9090")
        self.alertmanager_url = self.config.get("alertmanager_url", "http://localhost:9093")
        self.auth_headers = self._build_auth_headers()
        super().__init__(config)
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="prometheus_alerts",
            name="Prometheus Alerts",
            description="Query active alerts from Prometheus and Alertmanager. Shows current firing alerts and their details.",
            inputs={
                "source": "string - Alert source: 'prometheus' or 'alertmanager' (default: prometheus)",
                "state": "string - Alert state filter for alertmanager: 'active', 'suppressed', 'inhibited' (optional)",
                "filter": "string - Label filter for alertmanager (e.g., 'alertname=HighErrorRate') (optional)"
            },
            category="alerts"
        )
    
    def _validate_config(self) -> None:
        """Validate Prometheus alerts tool configuration."""
        if not self.base_url and not self.alertmanager_url:
            raise RuntimeError("Either Prometheus or Alertmanager URL must be configured")
    
    def _build_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers."""
        headers = {"Content-Type": "application/json"}
        
        username = self.config.get("username")
        password = self.config.get("password")
        if username and password:
            import base64
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
        
        token = self.config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        return headers
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute alerts query."""
        try:
            self.validate_inputs(inputs)
            
            source = inputs.get("source", "prometheus")
            state_filter = inputs.get("state")
            label_filter = inputs.get("filter")
            
            if source == "prometheus":
                return await self._query_prometheus_alerts()
            elif source == "alertmanager":
                return await self._query_alertmanager_alerts(state_filter, label_filter)
            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error_message=f"Invalid source: {source}. Use 'prometheus' or 'alertmanager'"
                )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Alerts query failed: {str(e)}"
            )
    
    async def _query_prometheus_alerts(self) -> ToolResult:
        """Query alerts from Prometheus."""
        url = f"{self.base_url}/api/v1/alerts"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self.auth_headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    return ToolResult(
                        success=False,
                        data=None,
                        error_message=f"Prometheus alerts query failed: HTTP {response.status} - {error_text}"
                    )
                
                response_data = await response.json()
                
                if response_data.get("status") != "success":
                    return ToolResult(
                        success=False,
                        data=None,
                        error_message=f"Prometheus alerts query failed: {response_data.get('error')}"
                    )
                
                alerts = response_data.get("data", {}).get("alerts", [])
                
                return ToolResult(
                    success=True,
                    data={
                        "source": "prometheus",
                        "alert_count": len(alerts),
                        "alerts": alerts
                    },
                    metadata={
                        "query_time": datetime.now().isoformat(),
                        "prometheus_url": url
                    }
                )
    
    async def _query_alertmanager_alerts(self, state_filter: Optional[str], label_filter: Optional[str]) -> ToolResult:
        """Query alerts from Alertmanager."""
        url = f"{self.alertmanager_url}/api/v1/alerts"
        
        params = {}
        if state_filter:
            params["filter"] = f"state={state_filter}"
        if label_filter:
            existing_filter = params.get("filter", "")
            if existing_filter:
                params["filter"] += f",{label_filter}"
            else:
                params["filter"] = label_filter
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                headers=self.auth_headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    return ToolResult(
                        success=False,
                        data=None,
                        error_message=f"Alertmanager query failed: HTTP {response.status} - {error_text}"
                    )
                
                alerts = await response.json()
                
                # Group alerts by state
                alert_states = {}
                for alert in alerts:
                    state = alert.get("status", {}).get("state", "unknown")
                    if state not in alert_states:
                        alert_states[state] = []
                    alert_states[state].append(alert)
                
                return ToolResult(
                    success=True,
                    data={
                        "source": "alertmanager",
                        "total_alerts": len(alerts),
                        "alerts_by_state": alert_states,
                        "alerts": alerts
                    },
                    metadata={
                        "query_time": datetime.now().isoformat(),
                        "alertmanager_url": url,
                        "filters": params
                    }
                )


class PrometheusTargetsTool(BaseTool):
    """Tool for checking Prometheus targets and service discovery."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.base_url = self.config.get("prometheus_url", "http://localhost:9090")
        self.auth_headers = self._build_auth_headers()
        super().__init__(config)
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="prometheus_targets",
            name="Prometheus Targets",
            description="Check status of Prometheus targets and service discovery. Shows which services are being monitored.",
            inputs={
                "state": "string - Target state filter: 'active', 'dropped', 'any' (default: active)"
            },
            category="health"
        )
    
    def _validate_config(self) -> None:
        """Validate configuration."""
        if not self.base_url:
            raise RuntimeError("Prometheus URL must be configured")
    
    def _build_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers."""
        headers = {"Content-Type": "application/json"}
        
        username = self.config.get("username")
        password = self.config.get("password")
        if username and password:
            import base64
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
        
        token = self.config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        return headers
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute targets query."""
        try:
            self.validate_inputs(inputs)
            
            state_filter = inputs.get("state", "active")
            url = f"{self.base_url}/api/v1/targets"
            
            params = {}
            if state_filter != "any":
                params["state"] = state_filter
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self.auth_headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        return ToolResult(
                            success=False,
                            data=None,
                            error_message=f"Prometheus targets query failed: HTTP {response.status} - {error_text}"
                        )
                    
                    response_data = await response.json()
                    
                    if response_data.get("status") != "success":
                        return ToolResult(
                            success=False,
                            data=None,
                            error_message=f"Prometheus targets query failed: {response_data.get('error')}"
                        )
                    
                    targets = response_data.get("data", {}).get("activeTargets", [])
                    
                    # Analyze target health
                    healthy_targets = 0
                    unhealthy_targets = 0
                    
                    for target in targets:
                        if target.get("health") == "up":
                            healthy_targets += 1
                        else:
                            unhealthy_targets += 1
                    
                    return ToolResult(
                        success=True,
                        data={
                            "state_filter": state_filter,
                            "total_targets": len(targets),
                            "healthy_targets": healthy_targets,
                            "unhealthy_targets": unhealthy_targets,
                            "targets": targets
                        },
                        metadata={
                            "query_time": datetime.now().isoformat(),
                            "prometheus_url": url
                        }
                    )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Targets query failed: {str(e)}"
            ) 