#!/usr/bin/env python3
"""
Main entry point for the Hands production debugging agent.
"""

import asyncio
import os
import sys
import logging
from hands import run_hands_plan

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for the Hands agent."""
    print("🚨 Hands - Production Debugging Agent")
    print("=" * 50)
    
    # Get the user's debugging goal
    user_goal = os.environ.get("HANDS_QUERY")
    if not user_goal:
        print("\nWhat production issue would you like me to investigate?")
        print("Examples:")
        print("  - 'Debug high error rate in payment service'")
        print("  - 'Investigate slow response times in user-api'")
        print("  - 'Analyze recent spike in 500 errors'")
        print("  - 'Check why checkout service is failing'")
        print()
        user_goal = input("Enter your debugging goal: ").strip()
        
        if not user_goal:
            print("❌ No debugging goal provided. Exiting.")
            return
    
    print(f"\n🔍 Investigating: {user_goal}")
    print("=" * 50)
    
    try:
        # Run the debugging investigation
        summary = await run_hands_plan(user_goal)
        
        print("\n" + "=" * 50)
        print("📊 INVESTIGATION SUMMARY")
        print("=" * 50)
        print(summary)
        
    except KeyboardInterrupt:
        print("\n⏹️  Investigation interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Investigation failed: {e}")
        print(f"\n❌ Investigation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0) 