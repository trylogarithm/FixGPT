#!/usr/bin/env python3
"""
Configuration validation script for fixgpt.
Run this to validate your config.yaml file before starting the agent.
"""

import sys
import os
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from config_loader import ConfigLoader


def main():
    """Validate fixgpt configuration."""
    print("🔧 fixgpt Configuration Validator")
    print("=" * 40)
    
    # Check if config file exists
    config_path = Path("config.yaml")
    if not config_path.exists():
        print("❌ No config.yaml found in current directory")
        print("📝 Create a config.yaml file using the example in README.md")
        return 1
    
    print(f"📁 Found config file: {config_path}")
    
    # Load and validate configuration
    try:
        config_loader = ConfigLoader()
        print(f"✅ Configuration loaded successfully")
        print(f"🌍 Environment: {config_loader.environment}")
        
        # Show enabled tools
        enabled_tools = config_loader.get_enabled_tools()
        if enabled_tools:
            print(f"🔧 Enabled tools: {', '.join(enabled_tools)}")
        else:
            print("⚠️  No tools are enabled!")
        
        # Show global settings
        global_config = config_loader.get_global_config()
        print(f"⚙️  Global settings:")
        print(f"   - Max steps: {config_loader.get_max_steps()}")
        print(f"   - Output dir: {config_loader.get_output_directory()}")
        print(f"   - Log level: {config_loader.get_log_level()}")
        
        # Validate configuration
        print("\n🔍 Validating configuration...")
        issues = config_loader.validate_config()
        
        if not issues:
            print("✅ Configuration is valid!")
            return 0
        else:
            print(f"⚠️  Found {len(issues)} issues:")
            for issue in issues:
                if issue.startswith("ERROR"):
                    print(f"❌ {issue}")
                else:
                    print(f"⚠️  {issue}")
            
            # Return error code if there are any ERROR issues
            error_count = sum(1 for issue in issues if issue.startswith("ERROR"))
            return 1 if error_count > 0 else 0
            
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    
    if exit_code == 0:
        print("\n🎉 Configuration validation passed!")
        print("🚀 You can now run: python main.py")
    else:
        print("\n💥 Configuration validation failed!")
        print("📖 Check the README.md for configuration examples")
    
    sys.exit(exit_code) 