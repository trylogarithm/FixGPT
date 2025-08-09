from typing import TypedDict
import json
from datetime import datetime
import os
from langchain_openai import ChatOpenAI
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

logger = logging.getLogger(__name__)


class ToolMetadata(TypedDict):
    id: str
    name: str
    inputs: dict[str, str]
    description: str


class PlanStep(TypedDict):
    id: str
    tool: str
    inputs: dict


class PlanningState(TypedDict):
    user_input: str
    current_plan: list[PlanStep]
    tool_metadata: list[ToolMetadata]
    done: bool
    history: list[dict]


def get_tool_metadata() -> list[ToolMetadata]:
    """
    Returns metadata for all available modular tools.
    """
    from tools import get_available_tools
    return get_available_tools()


def get_all_tool_metadata() -> list[ToolMetadata]:
    """
    Returns metadata for all available tools.
    """
    return get_tool_metadata()


def llm():
    return ChatOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-4o-mini",
        temperature=0.1
    )


async def plan_next_step(user_goal: str, tool_metadata: list[ToolMetadata], history: list[dict]) -> dict:
    """
    Plan the next step given the user goal, tool metadata, and history of steps and outputs.
    Returns a dict representing the next step, or the string 'PLAN COMPLETE'.
    """
    tool_list_str = "\n".join(
        f"- {tool.name}: {tool.description} (inputs: {', '.join(tool.inputs.keys())})"
        for tool in tool_metadata
    )
    
    history_str = json.dumps(history, indent=2)
    
    messages = [
        SystemMessage(content=(
            """You are a brains for a production debugging bot that analyzes logs, metrics, and alerts from multiple data sources.
            You generate step-by-step plans to investigate and debug production issues using modular observability tools.
            
            AVAILABLE DATA SOURCES:
            - Kubernetes logs via kubectl (k8s_logs, k8s_service_health)
            - Grafana Loki for log queries (loki_logs, loki_metrics) 
            - Prometheus for metrics and alerts (prometheus_query, prometheus_alerts, prometheus_targets)
            - Git repository history (git_commit_history, git_deployment_analysis)
            
            Generate only ONE step at a time based on the user goal and previous findings.
            
            IMPORTANT GUIDELINES:
            1. DISCOVERY FIRST: Always start by discovering what services/pods actually exist using kubectl_command "get pods" or "get svc"
            2. Use actual service names from discovery - never assume or make up service names
            3. Use the right tool for the job - kubectl_events for critical issues, K8s for container logs, Prometheus for metrics
            4. Look for patterns across data sources - correlate events with logs and metrics
            5. Follow the evidence - if you find critical events, investigate those specific services
            6. Be thorough - check multiple data sources when needed
            7. NAMESPACE DETECTION: 
               - If query mentions "otel-demo", "OpenTelemetry", or "demo", use namespace "otel-demo"
               - If query mentions specific namespace, use that namespace
               - For general queries, start with "default" namespace
            8. CRITICAL ISSUE PRIORITIES: OOMKilled > Probe Failures > Image Pull Errors > Network Issues > Performance
            
            DEBUGGING STRATEGY:
            - ALWAYS START: Use kubectl_command to discover actual services/pods in the namespace first
            - For alerts: Check prometheus alerts → Service health → Recent error logs → Git commit history → Metrics analysis
            - For service issues: Discover services → K8s service health → kubectl_events for critical issues → Recent logs → Connectivity testing
            - For performance issues: Discover services → Prometheus metrics → kubectl_events for OOM/restarts → K8s logs → Service dependencies
            - For deployment issues: Discover services → kubectl_events for failures → Git deployment analysis → Service health → Logs correlation
            - For infrastructure analysis: kubectl_command to list pods/services → kubectl_events for critical issues → Service connectivity testing
            - For log analysis: Start with kubectl_events for critical issues, then K8s logs, correlate with recent commits
            
            For each step, respond ONLY with a JSON object:
            {{"id": "stepN", "tool": "tool_name", "inputs": {{...}}}}
            
            If investigation is complete, respond with: 'PLAN COMPLETE'
            
            Current Time: {current_time}
            """
        ).format(current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))),
        HumanMessage(content=f"User goal: {user_goal}"),
        AIMessage(content=f"History of steps and outputs:\n{history_str}"),
        AIMessage(content=f"Available tools:\n{tool_list_str}"),
    ]
    
    response: AIMessage = await llm().ainvoke(messages)
    content = response.content.strip()
    
    if "PLAN COMPLETE" in content:
        return "PLAN COMPLETE"
    
    try:
        # Extract JSON from potential code blocks
        import re
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if match:
            content = match.group(1)
        
        step = json.loads(content)
        return step
    except Exception as e:
        logger.error(f"Failed to parse LLM output as JSON: {content} | Error: {e}")
        return "PLAN COMPLETE"