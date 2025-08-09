import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Configuration loader for fixgpt tool settings."""
    
    def __init__(self, config_path: str = "config.yaml", environment: Optional[str] = None):
        """
        Initialize configuration loader.
        
        Args:
            config_path: Path to YAML configuration file
            environment: Environment name for overrides (dev/staging/prod)
        """
        self.config_path = Path(config_path)
        self.environment = environment or os.getenv("fixgpt_ENV", "development")
        self._config = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        try:
            if not self.config_path.exists():
                logger.warning(f"Config file {self.config_path} not found, using defaults")
                self._config = self._get_default_config()
                return
            
            with open(self.config_path, 'r') as f:
                self._config = yaml.safe_load(f) or {}
            
            # Apply environment-specific overrides
            self._apply_environment_overrides()
            
            logger.info(f"Loaded configuration from {self.config_path} (env: {self.environment})")
            
        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            logger.info("Using default configuration")
            self._config = self._get_default_config()
    
    def _apply_environment_overrides(self) -> None:
        """Apply environment-specific configuration overrides."""
        if self.environment not in self._config:
            return
        
        env_config = self._config[self.environment]
        logger.info(f"Applying {self.environment} environment overrides")
        
        # Deep merge environment config
        self._deep_merge(self._config, env_config)
    
    def _deep_merge(self, base: Dict, override: Dict) -> None:
        """Deep merge override config into base config."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration when no config file is found."""
        return {
            "global": {
                "max_steps": 5,
                "output_directory": "agent_outputs",
                "log_level": "INFO"
            },
            "kubernetes": {"enabled": True},
            "loki": {"enabled": False},
            "prometheus": {"enabled": False},
            "git": {"enabled": True}
        }
    
    def is_tool_enabled(self, tool_name: str) -> bool:
        """
        Check if a tool is enabled.
        
        Args:
            tool_name: Name of the tool (kubernetes, loki, prometheus, git)
            
        Returns:
            True if tool is enabled, False otherwise
        """
        return self._config.get(tool_name, {}).get("enabled", False)
    
    def get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool configuration dictionary
        """
        tool_config = self._config.get(tool_name, {})
        
        # Merge connection and query_defaults into a flat config
        config = {}
        
        # Add connection settings
        if "connection" in tool_config:
            config.update(tool_config["connection"])
        
        # Add query defaults
        if "query_defaults" in tool_config:
            config.update(tool_config["query_defaults"])
        
        # Add other settings
        for key, value in tool_config.items():
            if key not in ["connection", "query_defaults", "enabled"]:
                config[key] = value
        
        return config
    
    def get_global_config(self) -> Dict[str, Any]:
        """Get global configuration settings."""
        return self._config.get("global", {})
    
    def get_max_steps(self) -> int:
        """Get maximum number of investigation steps."""
        return self.get_global_config().get("max_steps", 5)
    
    def get_output_directory(self) -> str:
        """Get output directory for agent results."""
        return self.get_global_config().get("output_directory", "agent_outputs")
    
    def get_log_level(self) -> str:
        """Get logging level."""
        return self.get_global_config().get("log_level", "INFO")
    
    def get_enabled_tools(self) -> list[str]:
        """
        Get list of enabled tool names.
        
        Returns:
            List of enabled tool names
        """
        enabled_tools = []
        tool_names = ["kubernetes", "loki", "prometheus", "git"]
        
        for tool_name in tool_names:
            if self.is_tool_enabled(tool_name):
                enabled_tools.append(tool_name)
        
        return enabled_tools
    
    def validate_config(self) -> list[str]:
        """
        Validate configuration and return list of warnings/errors.
        
        Returns:
            List of validation messages
        """
        issues = []
        
        # Check if at least one tool is enabled
        enabled_tools = self.get_enabled_tools()
        if not enabled_tools:
            issues.append("WARNING: No tools are enabled")
        
        # Validate tool-specific requirements
        if self.is_tool_enabled("loki"):
            loki_config = self.get_tool_config("loki")
            if not loki_config.get("url"):
                issues.append("ERROR: Loki is enabled but no URL configured")
        
        if self.is_tool_enabled("prometheus"):
            prometheus_config = self.get_tool_config("prometheus") 
            if not prometheus_config.get("prometheus_url"):
                issues.append("ERROR: Prometheus is enabled but no prometheus_url configured")
        
        if self.is_tool_enabled("git"):
            git_config = self.get_tool_config("git")
            repo_path = git_config.get("repo_path", ".")
            if not Path(repo_path).exists():
                issues.append(f"WARNING: Git repo_path '{repo_path}' does not exist")
        
        return issues
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()
    
    def __str__(self) -> str:
        """String representation of configuration."""
        enabled_tools = self.get_enabled_tools()
        return f"fixgpt Config (env: {self.environment}, tools: {enabled_tools})"


# Global configuration instance
config = ConfigLoader()


def get_config() -> ConfigLoader:
    """Get the global configuration instance."""
    return config


def reload_config() -> None:
    """Reload the global configuration."""
    global config
    config.reload() 