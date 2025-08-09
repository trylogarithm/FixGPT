import asyncio
import aiohttp
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import urllib.parse

from .base_tool import BaseTool, ToolMetadata, ToolResult


class LokiLogsTool(BaseTool):
    """Tool for querying logs from Grafana Loki."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Loki logs tool."""
        super().__init__(config)
        self.base_url = self.config.get("loki_url", "http://localhost:3100")
        self.auth_headers = self._build_auth_headers()
    
    @property
    def metadata(self) -> ToolMetadata:
        """Return metadata for Loki logs tool."""
        return ToolMetadata(
            id="loki_logs",
            name="Loki Logs Query",
            description="Query logs from Grafana Loki using LogQL. Supports real-time log streaming and historical queries.",
            inputs={
                "query": "string - LogQL query string (e.g., '{service=\"my-app\"} |= \"error\"')",
                "start_time": "string - Start time (ISO format or relative like '1h') (optional)",
                "end_time": "string - End time (ISO format) (optional, defaults to now)",
                "limit": "integer - Maximum number of log lines to return (default: 100)",
                "direction": "string - Query direction: 'forward' or 'backward' (default: backward)",
                "step": "string - Step size for range queries (e.g., '1m', '5m') (optional)"
            },
            category="logs"
        )
    
    def _validate_config(self) -> None:
        """Validate Loki tool configuration."""
        if not self.base_url:
            raise RuntimeError("Loki URL must be configured")
        
        # Optional: Test connectivity
        try:
            import requests
            response = requests.get(f"{self.base_url}/ready", timeout=5)
            if response.status_code != 200:
                raise RuntimeError(f"Loki not ready: {response.status_code}")
        except Exception as e:
            # Don't fail validation for connectivity issues in case Loki is behind auth
            pass
    
    def _build_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers for Loki requests."""
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
        """Execute Loki logs query."""
        try:
            self.validate_inputs(inputs)
            
            query = inputs["query"]
            start_time = inputs.get("start_time")
            end_time = inputs.get("end_time")
            limit = inputs.get("limit", 100)
            direction = inputs.get("direction", "backward")
            step = inputs.get("step")
            
            # Prepare time parameters
            end_ts = self._parse_time(end_time) if end_time else datetime.now()
            start_ts = self._parse_time(start_time) if start_time else end_ts - timedelta(hours=1)
            
            # Build query parameters
            params = {
                "query": query,
                "limit": str(limit),
                "direction": direction,
                "start": str(int(start_ts.timestamp() * 1_000_000_000)),  # nanoseconds
                "end": str(int(end_ts.timestamp() * 1_000_000_000))
            }
            
            # Choose endpoint based on query type
            if step:
                # Range query for metrics/aggregations
                endpoint = "/loki/api/v1/query_range"
                params["step"] = step
            else:
                # Instant query for logs
                endpoint = "/loki/api/v1/query_range"
            
            url = f"{self.base_url}{endpoint}"
            
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
                            error_message=f"Loki query failed: HTTP {response.status} - {error_text}"
                        )
                    
                    response_data = await response.json()
                    
                    # Parse Loki response
                    parsed_logs = self._parse_loki_response(response_data)
                    
                    return ToolResult(
                        success=True,
                        data={
                            "query": query,
                            "start_time": start_ts.isoformat(),
                            "end_time": end_ts.isoformat(),
                            "log_count": len(parsed_logs),
                            "logs": parsed_logs,
                            "raw_response_stats": response_data.get("data", {}).get("stats", {})
                        },
                        metadata={
                            "query_time": datetime.now().isoformat(),
                            "loki_url": url,
                            "query_params": params
                        }
                    )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Loki query execution failed: {str(e)}"
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
    
    def _parse_loki_response(self, response_data: dict) -> List[dict]:
        """Parse Loki API response into structured log entries."""
        log_entries = []
        
        result_type = response_data.get("data", {}).get("resultType")
        result = response_data.get("data", {}).get("result", [])
        
        for stream in result:
            stream_labels = stream.get("stream", {})
            values = stream.get("values", [])
            
            for value in values:
                timestamp_ns, log_line = value
                timestamp = datetime.fromtimestamp(int(timestamp_ns) / 1_000_000_000)
                
                # Try to extract log level from the log line
                log_level = "INFO"
                for level in ['ERROR', 'WARN', 'INFO', 'DEBUG', 'TRACE']:
                    if level in log_line.upper():
                        log_level = level
                        break
                
                log_entries.append({
                    "timestamp": timestamp.isoformat(),
                    "log_level": log_level,
                    "message": log_line,
                    "labels": stream_labels,
                    "raw_timestamp": timestamp_ns
                })
        
        # Sort by timestamp (most recent first)
        log_entries.sort(key=lambda x: x["raw_timestamp"], reverse=True)
        
        return log_entries


class LokiMetricsTool(BaseTool):
    """Tool for querying metrics from Grafana Loki using LogQL metric queries."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get("loki_url", "http://localhost:3100")
        self.auth_headers = self._build_auth_headers()
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="loki_metrics",
            name="Loki Metrics Query",
            description="Query metrics from Grafana Loki using LogQL metric queries. Useful for log-based metrics and aggregations.",
            inputs={
                "query": "string - LogQL metric query (e.g., 'rate({service=\"my-app\"} |= \"error\" [5m])')",
                "start_time": "string - Start time (ISO format or relative like '1h') (optional)",
                "end_time": "string - End time (ISO format) (optional, defaults to now)",
                "step": "string - Step size for range queries (e.g., '1m', '5m') (default: 1m)"
            },
            category="metrics"
        )
    
    def _validate_config(self) -> None:
        """Validate Loki tool configuration."""
        if not self.base_url:
            raise RuntimeError("Loki URL must be configured")
    
    def _build_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers for Loki requests."""
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
        """Execute Loki metrics query."""
        try:
            self.validate_inputs(inputs)
            
            query = inputs["query"]
            start_time = inputs.get("start_time")
            end_time = inputs.get("end_time")
            step = inputs.get("step", "1m")
            
            # Prepare time parameters
            end_ts = self._parse_time(end_time) if end_time else datetime.now()
            start_ts = self._parse_time(start_time) if start_time else end_ts - timedelta(hours=1)
            
            params = {
                "query": query,
                "start": str(int(start_ts.timestamp() * 1_000_000_000)),
                "end": str(int(end_ts.timestamp() * 1_000_000_000)),
                "step": step
            }
            
            url = f"{self.base_url}/loki/api/v1/query_range"
            
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
                            error_message=f"Loki metrics query failed: HTTP {response.status} - {error_text}"
                        )
                    
                    response_data = await response.json()
                    parsed_metrics = self._parse_metrics_response(response_data)
                    
                    return ToolResult(
                        success=True,
                        data={
                            "query": query,
                            "start_time": start_ts.isoformat(),
                            "end_time": end_ts.isoformat(),
                            "step": step,
                            "metrics": parsed_metrics,
                            "raw_response_stats": response_data.get("data", {}).get("stats", {})
                        },
                        metadata={
                            "query_time": datetime.now().isoformat(),
                            "loki_url": url
                        }
                    )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Loki metrics query failed: {str(e)}"
            )
    
    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string to datetime object."""
        # Same implementation as LokiLogsTool._parse_time
        if not time_str:
            return datetime.now()
        
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
            
            return datetime.now() - delta
        
        try:
            return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except ValueError:
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S']:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse time string: {time_str}")
    
    def _parse_metrics_response(self, response_data: dict) -> List[dict]:
        """Parse Loki metrics response into structured format."""
        metrics = []
        
        result = response_data.get("data", {}).get("result", [])
        
        for series in result:
            metric_labels = series.get("metric", {})
            values = series.get("values", [])
            
            parsed_values = []
            for timestamp, value in values:
                parsed_values.append({
                    "timestamp": datetime.fromtimestamp(float(timestamp)).isoformat(),
                    "value": float(value)
                })
            
            metrics.append({
                "labels": metric_labels,
                "values": parsed_values
            })
        
        return metrics 