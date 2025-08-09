<div align="center">

# FixGPT - AI Agent to Auto-Fix Production Issues

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://claude.ai/chat/b5f333c8-21c0-4cdc-a5c7-b88abaeab25d) [![License](https://img.shields.io/badge/license-MIT-green)](https://claude.ai/chat/b5f333c8-21c0-4cdc-a5c7-b88abaeab25d) [![Status](https://img.shields.io/badge/status-beta-yellow)](https://claude.ai/chat/b5f333c8-21c0-4cdc-a5c7-b88abaeab25d)

</div>

<div align="center">

FixGPT is an AI-powered production debugging agent that connects to your production stack to auto-debug issues, keeping your service running for longer.

</div>

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/trylogarithm/fixgpt.git
cd fixgpt
pip install -r requirements.txt

# Configure (minimal)
export OPENAI_API_KEY="your-key"
cp config.yaml.minimal config.yaml

# Run
python main.py

```

## Prerequisites

-   Python 3.8+
-   OpenAI API key with GPT-4 access
-   kubectl configured with appropriate permissions
-   [optional] Prometheus/Loki endpoints (if using metrics/logs tools

## Configuration

### Example Configuration for Local Development

```yaml
global:
  max_steps: 5
  log_level: "DEBUG"  # More verbose for local development
  output_directory: "agent_outputs"

kubernetes:
  enabled: true
  # The kubectl tool will use your default context
  # Make sure kubectl is configured for your local cluster

prometheus:
  enabled: true
  prometheus_url: "http://localhost:9090"

loki:
  enabled: true
  loki_url: "http://localhost:3100"

git:
  enabled: true
  repo_path: "."  # Current directory (the fixgpt project itself)
```

### Example Configuration for Production Development
```yaml
global:
  max_steps: 10  # More thorough investigation in production
  log_level: "INFO"
  output_directory: "/var/log/fixgpt/outputs"

kubernetes:
  enabled: true
  # Ensure kubectl is configured with production context
  # kubectl config use-context production-cluster

prometheus:
  enabled: true
  prometheus_url: "http://prometheus.monitoring.svc.cluster.local:9090"
  # For external Prometheus (if outside cluster):
  # prometheus_url: "https://prometheus.yourcompany.com"
  
  # Option 1: Bearer token
  token: "${PROMETHEUS_TOKEN}"
  
  # Option 2: Basic auth (uncomment if using basic auth instead)
  # username: "${PROMETHEUS_USER}"
  # password: "${PROMETHEUS_PASS}"

loki:
  enabled: true
  loki_url: "http://loki.monitoring.svc.cluster.local:3100"
  # For external Loki (if outside cluster):
  # loki_url: "https://loki.yourcompany.com"

  username: "${LOKI_USER}"
  password: "${LOKI_PASS}"
  

git:
  enabled: true
  repo_path: "/app" 

```
## Usage

### Basic Usage

Run the debugging agent and follow the prompts:

```bash
python main.py

```

### Set a Specific Query

```bash
export HANDS_QUERY="Debug high error rate in payment service"
python main.py

```

### Interactive Mode

```bash
python main.py --interactive

```

## 📚 Examples

### Debugging High Error Rate

```bash
export HANDS_QUERY="Debug 500 errors spike in payment-service since 2 hours ago"
python main.py

```

### Memory Leak Investigation

```bash
export HANDS_QUERY="Investigate memory leak in user-service pods"
python main.py

```

### Post-Deployment Issues

```bash
export HANDS_QUERY="Check for issues after deployment of order-service v2.3.1"
python main.py

```

### Database Performance Issues

```bash
export HANDS_QUERY="Analyze slow queries affecting checkout service"
python main.py

```

## Brain and Hands Architecture

FixGPT uses a dual-component architecture inspired by the separation of planning and execution:

### Architecture Flow

```
User Query → [🧠 Brain] → Investigation Plan
                ↓
         [🤲 Hands] → Execute Tools
                ↓
         [📊 Results] → Analysis
                ↓
         [🧠 Brain] → Next Steps / Summary

```

### 🧠 **Brain Component** (`brain.py`)

The Brain is the strategic planner that:

-   **Plans Investigation Steps**: Uses GPT-4o-mini to generate step-by-step debugging plans based on the user's goal
-   **Analyzes Context**: Reviews tool metadata, previous findings, and investigation history
-   **Makes Decisions**: Determines what tools to use next and how to focus the investigation
-   **Guides Strategy**: Follows production debugging best practices (discovery → analysis → correlation → resolution)

### 🤲 **Hands Component** (`hands.py`)

The Hands is the execution engine that:

-   **Executes Actions**: Runs the specific debugging steps planned by the Brain
-   **Operates Tools**: Interfaces with Kubernetes, Prometheus, Loki, and Git tools
-   **Gathers Data**: Collects logs, metrics, alerts, and system information
-   **Reports Findings**: Provides structured analysis of what was discovered
-   **Maintains Context**: Tracks investigation progress and maintains conversation history

### How They Work Together

1.  **User Query** → Brain analyzes the production issue and creates an investigation plan
2.  **Brain Planning** → Generates next step based on current findings and available tools
3.  **Hands Execution** → Executes the planned step using appropriate observability tools
4.  **Results Analysis** → Hands analyzes findings and reports back to Brain
5.  **Iteration** → Process repeats until issue is resolved or investigation is complete
6.  **Summary Generation** → Brain creates a structured incident report with findings and recommendations

This separation allows for:

-   **Strategic Thinking**: Brain focuses on high-level debugging strategy
-   **Reliable Execution**: Hands ensures consistent tool usage and data collection
-   **Adaptive Investigation**: Brain can pivot strategy based on Hands' findings
-   **Comprehensive Coverage**: Systematic exploration of all relevant data sources

## Available Tools

FixGPT includes a comprehensive suite of modular tools for production debugging. Each tool can be enabled/disabled in the configuration file.

### 🔧 **Kubernetes Tools**

-   **`k8s_logs`** - Query container logs using kubectl with time windows and filtering
-   **`k8s_service_health`** - Check health status of services, pods, and deployments
-   **`kubectl_command`** - Execute direct kubectl commands for deep cluster inspection
-   **`kubectl_events`** - Analyze Kubernetes events with filtering for critical issues
-   **`service_connectivity`** - Test actual service connectivity and health endpoints

### 📊 **Prometheus Tools**

-   **`prometheus_query`** - Execute PromQL queries for metrics analysis (instant & range queries)
-   **`prometheus_alerts`** - Query active alerts from Prometheus and Alertmanager
-   **`prometheus_targets`** - Check status of Prometheus targets and service discovery

### 📝 **Loki Tools**

-   **`loki_logs`** - Query structured logs using LogQL with advanced filtering
-   **`loki_metrics`** - Extract metrics from logs for trend analysis and alerting

### 🔄 **Git Tools**

-   **`git_commit_history`** - Analyze recent commits to correlate code changes with issues
-   **`git_deployment_analysis`** - Track deployments and releases for incident correlation

## Sample Output

```
🧠 Planning investigation for: High error rate in payment service
📋 Step 1: Checking service health and pod status...
✓ Found 3 pods in CrashLoopBackOff state
📋 Step 2: Analyzing recent logs for errors...
✓ Identified database connection timeout errors
📋 Step 3: Checking recent deployments...
✓ Database migration deployed 2 hours ago
📋 Step 4: Correlating metrics with deployment time...
✓ Error spike matches deployment timestamp
...
📝 Summary: Database migration script holding locks causing timeouts

Recommendations:
1. Rollback database migration
2. Fix migration script to use online DDL
3. Implement canary deployments for database changes

```

## Adding Custom Tools

FixGPT's modular architecture makes it easy to add your own tools for additional data sources or custom debugging workflows.

### Creating a New Tool

1.  **Create your tool class** by extending `BaseTool`:

```python
from tools.base_tool import BaseTool, ToolMetadata, ToolResult
from typing import Dict, Any, Optional

class MyCustomTool(BaseTool):
    """Tool for querying my custom data source."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        # Initialize your tool's connections/clients here
        self.api_url = self.config.get("api_url", "http://localhost:8080")
    
    @property
    def metadata(self) -> ToolMetadata:
        """Define your tool's interface and capabilities."""
        return ToolMetadata(
            id="my_custom_tool",
            name="My Custom Data Source",
            description="Query data from my custom monitoring system",
            inputs={
                "query": "string - Query string for the custom API",
                "time_range": "string - Time range (e.g., '1h', '24h') (optional)",
                "limit": "integer - Maximum results to return (optional, default: 100)"
            },
            category="custom"  # Choose: logs, metrics, alerts, health, custom
        )
    
    def _validate_config(self) -> None:
        """Validate your tool's configuration."""
        if not self.api_url:
            raise RuntimeError("API URL must be configured")
        # Add any other validation logic here
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Implement your tool's core functionality."""
        try:
            self.validate_inputs(inputs)
            
            query = inputs["query"]
            time_range = inputs.get("time_range", "1h")
            limit = inputs.get("limit", 100)
            
            # Your tool's logic here
            # Example: Make API calls, process data, etc.
            result_data = await self._query_api(query, time_range, limit)
            
            return ToolResult(
                success=True,
                data=result_data,
                metadata={"query": query, "results_count": len(result_data)}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Custom tool error: {str(e)}"
            )
    
    async def _query_api(self, query: str, time_range: str, limit: int):
        """Your custom API interaction logic."""
        # Implement your data source integration
        pass

```

2.  **Register your tool** in `tools/__init__.py`:

```python
from .my_custom_tool import MyCustomTool

# Add to the initialization function
def initialize_default_tools(config_loader=None) -> ToolRegistry:
    # ... existing tool initialization ...
    
    # Add your custom tool
    if config_loader.is_tool_enabled('my_custom_source'):
        custom_config = config_loader.get_tool_config('my_custom_source')
        try:
            custom_tool = MyCustomTool(custom_config)
            tools_to_register.append(custom_tool)
            print("✓ My Custom Tool enabled")
        except Exception as e:
            print(f"✗ Failed to initialize My Custom Tool: {e}")

```

3.  **Add configuration** to your `config.yaml`:

```yaml
my_custom_source:
  enabled: true
  connection:
    api_url: "https://my-monitoring-system.com/api"
    api_key: "your-api-key"
    timeout: 30

```

4.  **Add agent wrapper** in `hands.py` (for Brain/Hands integration):

```python
# Add this to the create_agent_tool_wrapper function
elif tool_id == "my_custom_tool":
    async def my_custom_tool_function(
        query: str,
        time_range: Optional[str] = "1h",
        limit: Optional[int] = 100
    ):
        """Query my custom data source."""
        kwargs = {k: v for k, v in locals().items() if v is not None}
        try:
            result = await registry.execute_tool(tool_id, kwargs)
            if result.success:
                return result.data
            else:
                return {"error": result.error_message}
        except Exception as e:
            return {"error": str(e)}

    return function_tool(
        my_custom_tool_function,
        name_override="my_custom_tool",
        strict_mode=False
    )

```

Your custom tools will automatically integrate with the Brain/Hands architecture and be available for production debugging workflows.

## ⚡ Performance & Limitations

-   **Investigation Time**: Complex issues may take 2-5 minutes to fully investigate
-   **Context Window**: Very large log outputs may be truncated
-   **Concurrent Investigations**: Run one investigation at a time for best results
-   **Historical Data**: Limited by your metrics/logs retention policies
-   **API Rate Limits**: Subject to OpenAI API rate limits
-   **Tool Timeouts**: Default 30-second timeout per tool execution (configurable)

## 🔒 Security Considerations

-   **API Keys**: Store sensitive keys in environment variables or secret management systems
-   **Kubernetes RBAC**: Ensure the kubectl context has minimal required permissions (read-only recommended)
-   **Read-Only Access**: Configure tools with read-only access where possible
-   **Audit Logging**: Enable audit logging for production debugging sessions
-   **Network Security**: Use VPN/private networks for accessing production systems
-   **Data Privacy**: Be mindful of PII in logs and metrics when sharing debug outputs

## 🔧 Troubleshooting

### Common Issues

**Tool initialization failures**

-   Check your config.yaml has correct endpoints
-   Verify network connectivity to Prometheus/Loki
-   Ensure kubectl has proper permissions
-   Run `python validate_config.py` to check configuration

**"No tools available" error**

-   At least one tool category must be enabled in config.yaml
-   Check that tool dependencies are installed
-   Verify API endpoints are accessible

**Timeout errors**

-   Increase timeout values in tool configurations
-   Check if your queries are too broad (narrow time ranges)
-   Verify network latency to your monitoring systems

**OpenAI API errors**

-   Verify your API key is valid and has sufficient credits
-   Check rate limiting - implement backoff if needed
-   Ensure you're using a compatible model (GPT-4 recommended)

**Memory issues with large datasets**

-   Reduce the time range of queries
-   Decrease result limits in tool configurations
-   Consider upgrading system memory

## 🤝 Contributing

We welcome contributions! See our [Contributing Guide](https://claude.ai/chat/CONTRIBUTING.md) for details.

### Areas for Contribution

-   New tool integrations (DataDog, New Relic, CloudWatch, Grafana, Pager Duty)
-   Improved error analysis patterns
-   Additional debugging strategies
-   Documentation improvements
-   Test coverage improvements
-   Performance optimizations, such as log chunking

## Roadmap

-   [ ] Support for more observability platforms (DataDog, New Relic)
-   [ ] Auto-remediation capabilities
-   [ ] Slack/PagerDuty integration
-   [ ] Web UI for investigation monitoring
-   [ ] Multi-cluster support
-   [ ] Historical incident pattern learning
-   [ ] Automated runbook generation

## License

MIT License

## Support
-   **Email**: team@trylogarithm.dev
-   **Discord**: [Join our Discord](https://discord.gg/6vH43VNxZD)

----------

<div align="center"> Built with ❤️ for engineers everywhere </div>
