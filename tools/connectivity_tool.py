"""
Service Connectivity and Verification Tool.
"""

import asyncio
import subprocess
import json
from typing import Dict, Any, List
from .base_tool import BaseTool, ToolResult, ToolMetadata


class ServiceConnectivityTool(BaseTool):
    """Tool for testing actual service connectivity and functionality."""
    
    def __init__(self, config=None):
        super().__init__(config)
    
    @property 
    def metadata(self) -> ToolMetadata:
        """Return metadata describing this tool."""
        return ToolMetadata(
            id="service_connectivity",
            name="Service Connectivity Testing",
            description="Test actual service connectivity, health endpoints, and end-to-end functionality",
            inputs={
                "service_name": "Name of the service to test",
                "namespace": "Kubernetes namespace (optional, defaults to 'default')",
                "port": "Service port to test (optional, defaults to 8080)",
                "protocol": "Protocol to use: 'http' or 'https' (optional, defaults to 'http')",
                "health_path": "Health check endpoint path (optional, defaults to '/health')",
                "timeout_seconds": "Connection timeout in seconds (optional, defaults to 30)"
            },
            category="health"
        )
    
    def _validate_config(self) -> bool:
        """Validate tool configuration."""
        return True  # connectivity tool doesn't need special config
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Test service connectivity."""
        try:
            self.validate_inputs(inputs)
            
            service_name = inputs["service_name"]
            namespace = inputs.get("namespace", "default")
            port = inputs.get("port", 8080)
            protocol = inputs.get("protocol", "http")
            health_path = inputs.get("health_path", "/health")
            timeout = inputs.get("timeout_seconds", 30)
            
            results = {
                "service_name": service_name,
                "namespace": namespace,
                "tests": {}
            }
            
            # Test 1: DNS Resolution
            results["tests"]["dns_resolution"] = await self._test_dns_resolution(
                service_name, namespace
            )
            
            # Test 2: Port Connectivity
            results["tests"]["port_connectivity"] = await self._test_port_connectivity(
                service_name, namespace, port, timeout
            )
            
            # Test 3: HTTP Health Check
            if protocol in ["http", "https"]:
                results["tests"]["http_health"] = await self._test_http_health(
                    service_name, namespace, port, protocol, health_path, timeout
                )
            
            # Test 4: Service Discovery
            results["tests"]["service_discovery"] = await self._test_service_discovery(
                service_name, namespace
            )
            
            # Overall assessment
            results["overall_status"] = self._assess_overall_status(results["tests"])
            
            return ToolResult(
                success=True,
                data=results
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data={},
                error_message=f"Failed to test service connectivity: {str(e)}"
            )
    
    async def _test_dns_resolution(self, service_name: str, namespace: str) -> Dict[str, Any]:
        """Test DNS resolution for the service."""
        try:
            # Test from within cluster using kubectl exec
            test_cmd = [
                "kubectl", "run", "connectivity-test", "--rm", "-i", "--restart=Never",
                "--image=nicolaka/netshoot", "--namespace", namespace,
                "--", "nslookup", f"{service_name}.{namespace}.svc.cluster.local"
            ]
            
            result = await asyncio.create_subprocess_exec(
                *test_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": "DNS resolution successful",
                    "output": stdout.decode().strip()
                }
            else:
                return {
                    "status": "failed",
                    "message": "DNS resolution failed",
                    "error": stderr.decode().strip()
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"DNS test error: {str(e)}"
            }
    
    async def _test_port_connectivity(self, service_name: str, namespace: str, port: int, timeout: int) -> Dict[str, Any]:
        """Test port connectivity to the service."""
        try:
            # Test port connectivity using kubectl exec with netcat
            test_cmd = [
                "kubectl", "run", "port-test", "--rm", "-i", "--restart=Never",
                "--image=nicolaka/netshoot", "--namespace", namespace,
                "--", "nc", "-z", "-v", "-w", str(timeout), 
                f"{service_name}.{namespace}.svc.cluster.local", str(port)
            ]
            
            result = await asyncio.create_subprocess_exec(
                *test_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            output = stdout.decode() + stderr.decode()
            
            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": f"Port {port} is accessible",
                    "output": output.strip()
                }
            else:
                return {
                    "status": "failed",
                    "message": f"Port {port} is not accessible",
                    "error": output.strip()
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Port connectivity test error: {str(e)}"
            }
    
    async def _test_http_health(self, service_name: str, namespace: str, port: int, 
                               protocol: str, health_path: str, timeout: int) -> Dict[str, Any]:
        """Test HTTP health endpoint."""
        try:
            url = f"{protocol}://{service_name}.{namespace}.svc.cluster.local:{port}{health_path}"
            
            # Test HTTP endpoint using kubectl exec with curl
            test_cmd = [
                "kubectl", "run", "http-test", "--rm", "-i", "--restart=Never",
                "--image=curlimages/curl", "--namespace", namespace,
                "--", "curl", "-v", "-f", "--connect-timeout", str(timeout),
                "--max-time", str(timeout), url
            ]
            
            result = await asyncio.create_subprocess_exec(
                *test_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": f"HTTP health check successful at {health_path}",
                    "response": stdout.decode().strip(),
                    "url": url
                }
            else:
                return {
                    "status": "failed",
                    "message": f"HTTP health check failed at {health_path}",
                    "error": stderr.decode().strip(),
                    "url": url
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"HTTP health test error: {str(e)}"
            }
    
    async def _test_service_discovery(self, service_name: str, namespace: str) -> Dict[str, Any]:
        """Test if service is properly registered in Kubernetes."""
        try:
            # Get service details
            cmd = ["kubectl", "get", "service", service_name, "-n", namespace, "-o", "json"]
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                service_data = json.loads(stdout.decode())
                return {
                    "status": "success",
                    "message": "Service is registered in Kubernetes",
                    "service_type": service_data.get("spec", {}).get("type", "Unknown"),
                    "cluster_ip": service_data.get("spec", {}).get("clusterIP", "None"),
                    "ports": service_data.get("spec", {}).get("ports", [])
                }
            else:
                return {
                    "status": "failed",
                    "message": "Service not found in Kubernetes",
                    "error": stderr.decode().strip()
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Service discovery test error: {str(e)}"
            }
    
    def _assess_overall_status(self, tests: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall connectivity status."""
        passed = 0
        total = len(tests)
        critical_failures = []
        
        for test_name, test_result in tests.items():
            if test_result.get("status") == "success":
                passed += 1
            elif test_result.get("status") == "failed":
                if test_name in ["dns_resolution", "service_discovery"]:
                    critical_failures.append(test_name)
        
        success_rate = (passed / total) * 100 if total > 0 else 0
        
        if success_rate >= 80 and not critical_failures:
            overall_status = "healthy"
        elif success_rate >= 50:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "success_rate": success_rate,
            "passed_tests": passed,
            "total_tests": total,
            "critical_failures": critical_failures
        } 