"""
Modular tools package for the fixgpt system.

This package provides a modular architecture for different data source integrations:
- K8s logs via kubectl
- Grafana Loki logs and metrics
- Prometheus metrics and alerts
"""

from .base_tool import BaseTool, ToolMetadata, ToolResult, ToolRegistry, tool_registry
from .k8s_logs_tool import K8sLogsTool, K8sServiceHealthTool
from .kubectl_tool import KubectlTool, KubectlEventsTool
from .connectivity_tool import ServiceConnectivityTool
from .loki_tool import LokiLogsTool, LokiMetricsTool
from .prometheus_tool import PrometheusQueryTool, PrometheusAlertsTool, PrometheusTargetsTool
from .git_tool import GitCommitHistoryTool, GitDeploymentAnalysisTool

__all__ = [
    'BaseTool',
    'ToolMetadata', 
    'ToolResult',
    'ToolRegistry',
    'tool_registry',
    'K8sLogsTool',
    'K8sServiceHealthTool',
    'LokiLogsTool',
    'LokiMetricsTool',
    'PrometheusQueryTool',
    'PrometheusAlertsTool', 
    'PrometheusTargetsTool',
    'GitCommitHistoryTool',
    'GitDeploymentAnalysisTool',
    'initialize_default_tools',
    'get_available_tools'
]


def initialize_default_tools(config_loader=None) -> ToolRegistry:
    """
    Initialize and register enabled tools with the global registry.
    
    Args:
        config_loader: ConfigLoader instance (optional, will create default if None)
        
    Returns:
        The global tool registry with enabled tools registered
    """
    if config_loader is None:
        from config_loader import get_config
        config_loader = get_config()
    
    print(f"Initializing tools with config: {config_loader}")
    
    # Validate configuration
    validation_issues = config_loader.validate_config()
    for issue in validation_issues:
        print(issue)
    
    tools_to_register = []
    
    # K8s tools (if enabled)
    if config_loader.is_tool_enabled('kubernetes'):
        k8s_config = config_loader.get_tool_config('kubernetes')
        try:
            k8s_logs_tool = K8sLogsTool(k8s_config)
            k8s_health_tool = K8sServiceHealthTool(k8s_config)
            kubectl_tool = KubectlTool()
            kubectl_events_tool = KubectlEventsTool()
            connectivity_tool = ServiceConnectivityTool()
            tools_to_register.extend([k8s_logs_tool, k8s_health_tool, kubectl_tool, kubectl_events_tool, connectivity_tool])
            print("✓ Kubernetes tools enabled (including kubectl and connectivity testing)")
        except Exception as e:
            print(f"✗ Failed to initialize Kubernetes tools: {e}")
    else:
        print("- Kubernetes tools disabled")
    
    # Loki tools (if enabled)
    if config_loader.is_tool_enabled('loki'):
        loki_config = config_loader.get_tool_config('loki')
        try:
            loki_logs_tool = LokiLogsTool(loki_config)
            loki_metrics_tool = LokiMetricsTool(loki_config)
            tools_to_register.extend([loki_logs_tool, loki_metrics_tool])
            print("✓ Loki tools enabled")
        except Exception as e:
            print(f"✗ Failed to initialize Loki tools: {e}")
    else:
        print("- Loki tools disabled")
    
    # Prometheus tools (if enabled)
    if config_loader.is_tool_enabled('prometheus'):
        prometheus_config = config_loader.get_tool_config('prometheus')
        try:
            prometheus_query_tool = PrometheusQueryTool(prometheus_config)
            prometheus_alerts_tool = PrometheusAlertsTool(prometheus_config)
            prometheus_targets_tool = PrometheusTargetsTool(prometheus_config)
            tools_to_register.extend([prometheus_query_tool, prometheus_alerts_tool, prometheus_targets_tool])
            print("✓ Prometheus tools enabled")
        except Exception as e:
            print(f"✗ Failed to initialize Prometheus tools: {e}")
    else:
        print("- Prometheus tools disabled")
    
    # Git tools (if enabled)
    if config_loader.is_tool_enabled('git'):
        git_config = config_loader.get_tool_config('git')
        try:
            git_commit_tool = GitCommitHistoryTool(git_config)
            git_deployment_tool = GitDeploymentAnalysisTool(git_config)
            tools_to_register.extend([git_commit_tool, git_deployment_tool])
            print("✓ Git tools enabled")
        except Exception as e:
            print(f"✗ Failed to initialize Git tools: {e}")
    else:
        print("- Git tools disabled")
    
    # Register all successfully initialized tools
    for tool in tools_to_register:
        try:
            tool_registry.register_tool(tool)
        except Exception as e:
            print(f"Warning: Failed to register {tool.__class__.__name__}: {e}")
    
    enabled_count = len(tool_registry._tools)
    enabled_tools = [tool.metadata.name for tool in tool_registry._tools.values()]
    print(f"Successfully registered {enabled_count} tools: {enabled_tools}")
    
    return tool_registry


def get_available_tools() -> list[ToolMetadata]:
    """
    Get metadata for all currently registered tools.
    
    Returns:
        List of tool metadata
    """
    return tool_registry.list_tools()


def get_tools_by_category(category: str) -> list[BaseTool]:
    """
    Get all tools in a specific category.
    
    Args:
        category: Tool category ('logs', 'metrics', 'alerts', 'health')
        
    Returns:
        List of tools in the specified category
    """
    return tool_registry.get_tools_by_category(category) 