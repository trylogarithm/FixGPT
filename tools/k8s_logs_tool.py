import asyncio
import json
import subprocess
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from .base_tool import BaseTool, ToolMetadata, ToolResult


class K8sLogsTool(BaseTool):
    """Tool for querying Kubernetes cluster logs via kubectl."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize K8s logs tool."""
        super().__init__(config)
    
    @property
    def metadata(self) -> ToolMetadata:
        """Return metadata for K8s logs tool."""
        return ToolMetadata(
            id="k8s_logs",
            name="K8s Logs Query",
            description="Query logs from Kubernetes services using kubectl. Requires kubectl to be configured and authenticated.",
            inputs={
                "service_name": "string - Name of the Kubernetes service/deployment",
                "namespace": "string - Kubernetes namespace (default: default)",
                "time_window_minutes": "integer - Time window in minutes to query (default: 60)",
                "log_level": "string - Log level filter (ERROR/WARN/INFO/DEBUG) (optional)",
                "limit": "integer - Maximum number of log lines to return (default: 100)",
                "follow": "boolean - Whether to stream logs (default: false)"
            },
            category="logs"
        )
    
    def _validate_config(self) -> None:
        """Validate K8s tool configuration."""
        # Check if kubectl is available
        try:
            result = subprocess.run(
                ["kubectl", "version", "--client"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError("kubectl is not properly installed or configured")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"kubectl validation failed: {e}")
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute kubectl logs query."""
        try:
            self.validate_inputs(inputs)
            
            service_name = inputs["service_name"]
            namespace = inputs.get("namespace", "default")
            time_window_minutes = inputs.get("time_window_minutes", 60)
            log_level = inputs.get("log_level")
            limit = inputs.get("limit", 100)
            follow = inputs.get("follow", False)
            
            # Build kubectl command
            cmd = [
                "kubectl", "logs",
                f"deployment/{service_name}",
                f"--namespace={namespace}",
                f"--since={time_window_minutes}m",
                f"--tail={limit}"
            ]
            
            if follow:
                cmd.append("--follow")
            
            # Execute kubectl command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    data=None,
                    error_message=f"kubectl command failed: {stderr.decode()}"
                )
            
            logs = stdout.decode()
            
            # Filter by log level if specified
            if log_level:
                filtered_logs = []
                for line in logs.split('\n'):
                    if log_level.upper() in line.upper():
                        filtered_logs.append(line)
                logs = '\n'.join(filtered_logs)
            
            # Parse logs into structured format
            log_entries = self._parse_logs(logs, service_name, namespace)
            
            return ToolResult(
                success=True,
                data={
                    "service_name": service_name,
                    "namespace": namespace,
                    "time_window_minutes": time_window_minutes,
                    "log_count": len(log_entries),
                    "logs": log_entries
                },
                metadata={
                    "query_time": datetime.now().isoformat(),
                    "kubectl_command": " ".join(cmd)
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"K8s logs query failed: {str(e)}"
            )
    
    def _parse_logs(self, raw_logs: str, service_name: str, namespace: str) -> list:
        """Parse raw kubectl logs into structured format."""
        log_entries = []
        
        for line_num, line in enumerate(raw_logs.split('\n')):
            if not line.strip():
                continue
                
            # Try to extract timestamp and log level
            timestamp = None
            log_level = "INFO"
            message = line
            
            # Common log format parsing (ISO timestamp)
            try:
                if line.startswith(('20', '19')):  # Likely timestamp
                    parts = line.split(' ', 2)
                    if len(parts) >= 2:
                        timestamp = parts[0] + ' ' + parts[1]
                        message = parts[2] if len(parts) > 2 else ""
                        
                        # Extract log level
                        for level in ['ERROR', 'WARN', 'INFO', 'DEBUG']:
                            if level in message.upper():
                                log_level = level
                                break
            except:
                pass  # Keep defaults if parsing fails
            
            log_entries.append({
                "line_number": line_num + 1,
                "timestamp": timestamp,
                "log_level": log_level,
                "message": message,
                "service": service_name,
                "namespace": namespace,
                "raw_line": line
            })
        
        return log_entries


class K8sServiceHealthTool(BaseTool):
    """Tool for checking Kubernetes service health and status."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="k8s_service_health",
            name="K8s Service Health",
            description="Check health and status of Kubernetes services including pods, deployments, and events.",
            inputs={
                "service_name": "string - Name of the Kubernetes service/deployment", 
                "namespace": "string - Kubernetes namespace (default: default)"
            },
            category="health"
        )
    
    def _validate_config(self) -> None:
        """Validate K8s tool configuration."""
        try:
            result = subprocess.run(
                ["kubectl", "version", "--client"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError("kubectl is not properly installed or configured")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"kubectl validation failed: {e}")
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute service health check."""
        try:
            self.validate_inputs(inputs)
            
            service_name = inputs["service_name"]
            namespace = inputs.get("namespace", "default")
            
            # If service_name is empty, check all pods/services in namespace
            if not service_name or service_name.strip() == "":
                return await self._check_namespace_health(namespace)
            
            # Get deployment status
            deployment_cmd = [
                "kubectl", "get", "deployment", service_name,
                f"--namespace={namespace}", "-o", "json"
            ]
            
            # Get pods status
            pods_cmd = [
                "kubectl", "get", "pods",
                f"--namespace={namespace}",
                f"--selector=app={service_name}",
                "-o", "json"
            ]
            
            # Get recent events
            events_cmd = [
                "kubectl", "get", "events",
                f"--namespace={namespace}",
                "--sort-by=.lastTimestamp",
                "-o", "json"
            ]
            
            # Execute commands concurrently
            deployment_result = await self._run_kubectl_command(deployment_cmd)
            pods_result = await self._run_kubectl_command(pods_cmd)
            events_result = await self._run_kubectl_command(events_cmd)
            
            health_data = {
                "service_name": service_name,
                "namespace": namespace,
                "deployment_status": deployment_result,
                "pods_status": pods_result,
                "recent_events": self._filter_service_events(events_result, service_name),
                "overall_health": self._assess_health(deployment_result, pods_result)
            }
            
            return ToolResult(
                success=True,
                data=health_data,
                metadata={
                    "query_time": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"K8s service health check failed: {str(e)}"
            )
    
    async def _run_kubectl_command(self, cmd: list) -> dict:
        """Run kubectl command and return parsed JSON result."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return {"error": stderr.decode()}
        
        try:
            return json.loads(stdout.decode())
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response"}
    
    def _filter_service_events(self, events_data: dict, service_name: str) -> dict:
        """Filter events related to the specific service with enhanced critical issue detection."""
        if "error" in events_data or "items" not in events_data:
            return {"events": [], "critical_issues": {}}
        
        service_events = []
        critical_issues = {
            "oom_killed": [],
            "probe_failures": [],
            "image_pull_errors": [],
            "networking_issues": [],
            "restart_loops": []
        }
        
        for event in events_data["items"][-20:]:  # Last 20 events for better analysis
            event_obj_name = event.get("involvedObject", {}).get("name", "")
            
            if service_name in event_obj_name or event_obj_name == "":
                event_data = {
                    "time": event.get("lastTimestamp"),
                    "type": event.get("type"),
                    "reason": event.get("reason"),
                    "message": event.get("message"),
                    "object": event_obj_name
                }
                service_events.append(event_data)
                
                # Enhanced critical issue detection
                reason = event.get("reason", "")
                message = event.get("message", "").lower()
                event_type = event.get("type", "")
                
                if event_type == "Warning":
                    if "oomkilled" in reason.lower():
                        critical_issues["oom_killed"].append(event_data)
                    elif "probe failed" in message or "unhealthy" in reason.lower():
                        critical_issues["probe_failures"].append(event_data)
                    elif "imagepull" in reason.lower() or "errimagepull" in reason.lower():
                        critical_issues["image_pull_errors"].append(event_data)
                    elif any(keyword in message for keyword in ["connection refused", "timeout", "network", "dns"]):
                        critical_issues["networking_issues"].append(event_data)
                    elif "backoff" in reason.lower() or "crashloop" in reason.lower():
                        critical_issues["restart_loops"].append(event_data)
        
        return {
            "events": service_events,
            "critical_issues": critical_issues,
            "critical_summary": {
                "total_critical": sum(len(issues) for issues in critical_issues.values()),
                "has_oom_issues": len(critical_issues["oom_killed"]) > 0,
                "has_probe_issues": len(critical_issues["probe_failures"]) > 0,
                "has_network_issues": len(critical_issues["networking_issues"]) > 0
            }
        }
    
    def _assess_health(self, deployment_data: dict, pods_data: dict) -> str:
        """Assess overall service health based on deployment and pod status."""
        if "error" in deployment_data or "error" in pods_data:
            return "unknown"
        
        # Check deployment readiness
        if "status" in deployment_data:
            replicas = deployment_data["status"].get("replicas", 0)
            ready_replicas = deployment_data["status"].get("readyReplicas", 0)
            
            if ready_replicas == replicas and replicas > 0:
                return "healthy"
            elif ready_replicas > 0:
                return "degraded"
            else:
                return "unhealthy"
        
        return "unknown" 

    async def _check_namespace_health(self, namespace: str) -> ToolResult:
        """Check health of all pods and services in a namespace."""
        try:
            # Get all pods in namespace
            all_pods_cmd = [
                "kubectl", "get", "pods",
                f"--namespace={namespace}",
                "-o", "json"
            ]
            
            # Get all deployments in namespace
            all_deployments_cmd = [
                "kubectl", "get", "deployments",
                f"--namespace={namespace}",
                "-o", "json"
            ]
            
            # Get recent events
            events_cmd = [
                "kubectl", "get", "events",
                f"--namespace={namespace}",
                "--sort-by=.lastTimestamp",
                "-o", "json"
            ]
            
            # Execute commands
            pods_result = await self._run_kubectl_command(all_pods_cmd)
            deployments_result = await self._run_kubectl_command(all_deployments_cmd)
            events_result = await self._run_kubectl_command(events_cmd)
            
            # Analyze namespace health
            namespace_health = self._assess_namespace_health(pods_result, deployments_result, events_result)
            
            return ToolResult(
                success=True,
                data={
                    "namespace": namespace,
                    "check_type": "namespace_wide",
                    "pods_status": pods_result,
                    "deployments_status": deployments_result,
                    "recent_events": events_result.get("items", [])[-20:] if "items" in events_result else [],
                    "health_summary": namespace_health
                },
                metadata={
                    "query_time": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Namespace health check failed: {str(e)}"
            )
    
    def _assess_namespace_health(self, pods_result: dict, deployments_result: dict, events_result: dict) -> dict:
        """Assess overall namespace health."""
        health_summary = {
            "total_pods": 0,
            "running_pods": 0,
            "failed_pods": 0,
            "pending_pods": 0,
            "pod_issues": [],
            "total_deployments": 0,
            "healthy_deployments": 0,
            "unhealthy_deployments": 0,
            "recent_warnings": [],
            "overall_status": "unknown"
        }
        
        # Analyze pods
        if "items" in pods_result:
            health_summary["total_pods"] = len(pods_result["items"])
            
            for pod in pods_result["items"]:
                pod_name = pod.get("metadata", {}).get("name", "unknown")
                pod_status = pod.get("status", {}).get("phase", "unknown")
                
                if pod_status == "Running":
                    # Check if all containers are ready
                    container_statuses = pod.get("status", {}).get("containerStatuses", [])
                    all_ready = all(c.get("ready", False) for c in container_statuses)
                    if all_ready:
                        health_summary["running_pods"] += 1
                    else:
                        health_summary["failed_pods"] += 1
                        health_summary["pod_issues"].append({
                            "name": pod_name,
                            "issue": "containers_not_ready",
                            "status": pod_status
                        })
                elif pod_status == "Pending":
                    health_summary["pending_pods"] += 1
                    health_summary["pod_issues"].append({
                        "name": pod_name,
                        "issue": "pending",
                        "status": pod_status
                    })
                else:
                    health_summary["failed_pods"] += 1
                    health_summary["pod_issues"].append({
                        "name": pod_name,
                        "issue": "failed_status",
                        "status": pod_status
                    })
        
        # Analyze deployments
        if "items" in deployments_result:
            health_summary["total_deployments"] = len(deployments_result["items"])
            
            for deployment in deployments_result["items"]:
                dep_name = deployment.get("metadata", {}).get("name", "unknown")
                status = deployment.get("status", {})
                replicas = status.get("replicas", 0)
                ready_replicas = status.get("readyReplicas", 0)
                
                if ready_replicas == replicas and replicas > 0:
                    health_summary["healthy_deployments"] += 1
                else:
                    health_summary["unhealthy_deployments"] += 1
        
        # Extract recent warnings from events
        if "items" in events_result:
            for event in events_result["items"][-10:]:  # Last 10 events
                if event.get("type") == "Warning":
                    health_summary["recent_warnings"].append({
                        "time": event.get("lastTimestamp"),
                        "reason": event.get("reason"),
                        "message": event.get("message"),
                        "object": event.get("involvedObject", {}).get("name")
                    })
        
        # Determine overall status
        if health_summary["failed_pods"] == 0 and health_summary["unhealthy_deployments"] == 0:
            health_summary["overall_status"] = "healthy"
        elif health_summary["running_pods"] > 0:
            health_summary["overall_status"] = "degraded"
        else:
            health_summary["overall_status"] = "critical"
        
        return health_summary 