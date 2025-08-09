from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ToolMetadata:
    """Metadata describing a tool's capabilities and inputs."""
    id: str
    name: str
    description: str
    inputs: Dict[str, str]
    category: str  # 'logs', 'metrics', 'traces', etc.


@dataclass
class ToolResult:
    """Standardized result from tool execution."""
    success: bool
    data: Any
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseTool(ABC):
    """Base class for all modular tools in the system."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize tool with optional configuration."""
        self.config = config or {}
        self._validate_config()
    
    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Return metadata describing this tool."""
        pass
    
    @abstractmethod
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute the tool with given inputs."""
        pass
    
    @abstractmethod
    def _validate_config(self) -> None:
        """Validate the tool configuration. Raise exception if invalid."""
        pass
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs match the expected schema."""
        all_inputs = set(self.metadata.inputs.keys())
        provided_inputs = set(inputs.keys())
        
        # Determine required inputs (those without "optional" in description)
        required_inputs = set()
        for input_name, input_desc in self.metadata.inputs.items():
            # Check if the input description indicates it's optional
            if "optional" not in input_desc.lower():
                required_inputs.add(input_name)
        
        # Check if all required inputs are provided
        missing_inputs = required_inputs - provided_inputs
        if missing_inputs:
            raise ValueError(f"Missing required inputs: {missing_inputs}")
        
        return True


class ToolRegistry:
    """Registry for managing and discovering available tools."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool in the registry."""
        self._tools[tool.metadata.id] = tool
    
    def get_tool(self, tool_id: str) -> Optional[BaseTool]:
        """Get a tool by its ID."""
        return self._tools.get(tool_id)
    
    def list_tools(self) -> List[ToolMetadata]:
        """List metadata for all registered tools."""
        return [tool.metadata for tool in self._tools.values()]
    
    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """Get all tools in a specific category."""
        return [tool for tool in self._tools.values() 
                if tool.metadata.category == category]
    
    async def execute_tool(self, tool_id: str, inputs: Dict[str, Any]) -> ToolResult:
        """Execute a tool by ID with validation."""
        tool = self.get_tool(tool_id)
        if not tool:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Tool '{tool_id}' not found"
            )
        
        try:
            tool.validate_inputs(inputs)
            return await tool.execute(inputs)
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=str(e)
            )


# Global tool registry instance
tool_registry = ToolRegistry() 