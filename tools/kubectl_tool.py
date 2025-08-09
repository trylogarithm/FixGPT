"""
Kubectl Command Execution Tool for direct cluster inspection.
"""

import asyncio
import subprocess
import json
from typing import Dict, Any, List
from .base_tool import BaseTool, ToolResult, ToolMetadata


class KubectlTool(BaseTool):
    """Tool for executing kubectl commands directly against the cluster."""
    
    def __init__(self, config=None):
        super().__init__(config)
    
    @property
    def metadata(self) -> ToolMetadata:
        """Return metadata describing this tool."""
        return ToolMetadata(
            id="kubectl_command",
            name="Kubectl Command Execution",
            description="Execute kubectl commands directly for deep cluster inspection and verification",
            inputs={
                "command": "kubectl subcommand to execute (e.g., 'describe pod', 'get events', 'top nodes')",
                "namespace": "Kubernetes namespace (optional, defaults to 'default')",
                "output_format": "Output format: 'json', 'yaml', or 'text' (optional, defaults to 'text')",
                "additional_flags": "Additional kubectl flags (optional)"
            },
            category="health"
        )
    
    def _validate_config(self) -> bool:
        """Validate tool configuration."""
        return True  # kubectl tool doesn't need special config
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute kubectl command."""
        try:
            self.validate_inputs(inputs)
            
            command = inputs["command"]
            namespace = inputs.get("namespace", "default")
            output_format = inputs.get("output_format", "text")
            additional_flags = inputs.get("additional_flags", "")
            
            # Build kubectl command
            kubectl_cmd = ["kubectl"] + command.split()
            
            # Add namespace if not already specified
            if "--namespace" not in command and "-n" not in command and namespace != "default":
                kubectl_cmd.extend(["--namespace", namespace])
            
            # Add output format if specified
            if output_format in ["json", "yaml"] and "-o" not in command:
                kubectl_cmd.extend(["-o", output_format])
            
            # Add additional flags
            if additional_flags:
                kubectl_cmd.extend(additional_flags.split())
            
            # Execute command
            result = await asyncio.create_subprocess_exec(
                *kubectl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    data={},
                    error_message=f"kubectl command failed: {stderr.decode()}"
                )
            
            output = stdout.decode().strip()
            
            # Parse JSON output if requested
            if output_format == "json" and output:
                try:
                    parsed_output = json.loads(output)
                    # Limit output size to prevent context overflow
                    if len(output) > 10000:  # 10KB limit
                        summary = {
                            "truncated": True,
                            "total_items": len(parsed_output.get("items", [])) if "items" in parsed_output else 0,
                            "sample_items": parsed_output.get("items", [])[:3] if "items" in parsed_output else parsed_output
                        }
                        return ToolResult(
                            success=True,
                            data={
                                "command": " ".join(kubectl_cmd),
                                "output": summary,
                                "note": f"Output truncated (original size: {len(output)} chars, showing first 3 items)"
                            }
                        )
                    return ToolResult(
                        success=True,
                        data={
                            "command": " ".join(kubectl_cmd),
                            "output": parsed_output,
                            "raw_output": output[:1000] if len(output) > 1000 else output
                        }
                    )
                except json.JSONDecodeError:
                    pass
            
            return ToolResult(
                success=True,
                data={
                    "command": " ".join(kubectl_cmd),
                    "output": output,
                    "lines": output.split("\n") if output else []
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data={},
                error_message=f"Failed to execute kubectl command: {str(e)}"
            )


class KubectlEventsTool(BaseTool):
    """Tool for analyzing Kubernetes events with filtering capabilities."""
    
    def __init__(self, config=None):
        super().__init__(config)
    
    @property
    def metadata(self) -> ToolMetadata:
        """Return metadata describing this tool."""
        return ToolMetadata(
            id="kubectl_events",
            name="Kubernetes Events Analysis",
            description="Analyze Kubernetes events with filtering for OOMKilled, probe failures, and other critical events",
            inputs={
                "namespace": "Kubernetes namespace (optional, defaults to 'default')",
                "event_type": "Filter by event type: 'Warning', 'Normal', or 'all' (optional, defaults to 'all')",
                "reason_filter": "Filter by reason: 'OOMKilled', 'Unhealthy', 'BackOff', etc. (optional)",
                "time_window_minutes": "Time window to look back in minutes (optional, defaults to 60)",
                "limit": "Maximum number of events to return (optional, defaults to 50)"
            },
            category="health"
        )
    
    def _validate_config(self) -> bool:
        """Validate tool configuration."""
        return True  # events tool doesn't need special config
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Analyze Kubernetes events with filtering."""
        try:
            self.validate_inputs(inputs)
            
            namespace = inputs.get("namespace", "default")
            event_type = inputs.get("event_type", "all")
            reason_filter = inputs.get("reason_filter")
            time_window = inputs.get("time_window_minutes", 60)
            limit = inputs.get("limit", 50)
            
            # Build kubectl get events command
            kubectl_cmd = ["kubectl", "get", "events", "--sort-by=.lastTimestamp"]
            
            if namespace != "default":
                kubectl_cmd.extend(["--namespace", namespace])
            
            kubectl_cmd.extend(["-o", "json"])
            
            # Execute command
            result = await asyncio.create_subprocess_exec(
                *kubectl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    data={},
                    error_message=f"Failed to get events: {stderr.decode()}"
                )
            
            events_data = json.loads(stdout.decode())
            events = events_data.get("items", [])
            
            # Filter events
            filtered_events = []
            critical_events = []
            
            for event in events[-limit:]:  # Get latest events
                event_info = {
                    "timestamp": event.get("lastTimestamp", event.get("eventTime", "")),
                    "type": event.get("type", ""),
                    "reason": event.get("reason", ""),
                    "message": event.get("message", ""),
                    "object": f"{event.get('involvedObject', {}).get('kind', '')}/{event.get('involvedObject', {}).get('name', '')}",
                    "namespace": event.get("namespace", "")
                }
                
                # Apply filters
                if event_type != "all" and event_info["type"] != event_type:
                    continue
                
                if reason_filter and reason_filter.lower() not in event_info["reason"].lower():
                    continue
                
                filtered_events.append(event_info)
                
                # Identify critical events
                if event_info["reason"] in ["OOMKilled", "Unhealthy", "BackOff", "Failed"] or \
                   event_info["type"] == "Warning":
                    critical_events.append(event_info)
            
            # Summary analysis
            summary = {
                "total_events": len(filtered_events),
                "critical_events_count": len(critical_events),
                "oom_killed_count": len([e for e in critical_events if "OOM" in e["reason"]]),
                "probe_failures": len([e for e in critical_events if "probe failed" in e["message"].lower()]),
                "warning_events": len([e for e in filtered_events if e["type"] == "Warning"])
            }
            
            return ToolResult(
                success=True,
                data={
                    "summary": summary,
                    "filtered_events": filtered_events,
                    "critical_events": critical_events,
                    "analysis": self._analyze_events(critical_events)
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data={},
                error_message=f"Failed to analyze events: {str(e)}"
            )
    
    def _analyze_events(self, critical_events: List[Dict]) -> Dict[str, Any]:
        """Analyze critical events for patterns."""
        analysis = {
            "resource_issues": [],
            "connectivity_issues": [],
            "configuration_issues": [],
            "recommendations": []
        }
        
        for event in critical_events:
            if "OOMKilled" in event["reason"]:
                analysis["resource_issues"].append({
                    "type": "Memory limit exceeded",
                    "object": event["object"],
                    "message": event["message"]
                })
                analysis["recommendations"].append(f"Increase memory limit for {event['object']}")
            
            elif "probe failed" in event["message"].lower():
                if "connection refused" in event["message"].lower():
                    analysis["connectivity_issues"].append({
                        "type": "Service connectivity failure",
                        "object": event["object"],
                        "message": event["message"]
                    })
                else:
                    analysis["configuration_issues"].append({
                        "type": "Health probe configuration issue",
                        "object": event["object"],
                        "message": event["message"]
                    })
        
        return analysis 