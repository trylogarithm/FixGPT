import asyncio
import subprocess
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from .base_tool import BaseTool, ToolMetadata, ToolResult


class GitCommitHistoryTool(BaseTool):
    """Tool for querying Git commit history and analyzing code changes."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Git commit history tool."""
        super().__init__(config)
        self.repo_path = self.config.get("repo_path", ".")
    
    @property
    def metadata(self) -> ToolMetadata:
        """Return metadata for Git commit history tool."""
        return ToolMetadata(
            id="git_commit_history",
            name="Git Commit History",
            description="Query Git commit history to correlate code changes with production issues. Helps identify recent deployments and changes.",
            inputs={
                "since": "string - Time range (e.g., '1h', '2d', '1w') or ISO date (default: 24h)",
                "until": "string - End time (ISO date or relative) (optional, defaults to now)",
                "author": "string - Filter by commit author (optional)",
                "grep": "string - Search commit messages for keywords (optional)",
                "file_path": "string - Filter commits affecting specific file/directory (optional)",
                "limit": "integer - Maximum number of commits to return (default: 50)",
                "include_diff": "boolean - Include diff information (default: false)",
                "branch": "string - Branch to query (default: current branch)"
            },
            category="code"
        )
    
    def _validate_config(self) -> None:
        """Validate Git tool configuration."""
        # Check if git is available
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.repo_path
            )
            if result.returncode != 0:
                raise RuntimeError("Git is not properly installed")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(f"Git validation failed: {e}")
        
        # Check if we're in a git repository
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.repo_path
            )
            if result.returncode != 0:
                raise RuntimeError(f"Directory {self.repo_path} is not a git repository")
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Git repository check failed: {e}")
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute git commit history query."""
        try:
            self.validate_inputs(inputs)
            
            since = inputs.get("since", "24h")
            until = inputs.get("until")
            author = inputs.get("author")
            grep_pattern = inputs.get("grep")
            file_path = inputs.get("file_path")
            limit = inputs.get("limit", 50)
            include_diff = inputs.get("include_diff", False)
            branch = inputs.get("branch")
            
            # Build git log command
            cmd = ["git", "log", "--oneline", "--date=iso", "--format=fuller"]
            
            # Add time range
            if since:
                since_formatted = self._format_time_for_git(since)
                cmd.extend(["--since", since_formatted])
            
            if until:
                until_formatted = self._format_time_for_git(until)
                cmd.extend(["--until", until_formatted])
            
            # Add filters
            if author:
                cmd.extend(["--author", author])
            
            if grep_pattern:
                cmd.extend(["--grep", grep_pattern])
            
            if limit:
                cmd.extend([f"-{limit}"])
            
            if branch:
                cmd.append(branch)
            
            if file_path:
                cmd.extend(["--", file_path])
            
            # Execute git log command
            commits = await self._run_git_command(cmd)
            
            if not commits:
                return ToolResult(
                    success=True,
                    data={
                        "query_params": inputs,
                        "commit_count": 0,
                        "commits": [],
                        "summary": "No commits found matching the criteria"
                    }
                )
            
            # Parse commits
            parsed_commits = await self._parse_git_log_output(commits, include_diff)
            
            # Get additional statistics
            stats = await self._get_commit_stats(parsed_commits)
            
            return ToolResult(
                success=True,
                data={
                    "query_params": inputs,
                    "commit_count": len(parsed_commits),
                    "commits": parsed_commits,
                    "statistics": stats,
                    "summary": self._generate_summary(parsed_commits, stats)
                },
                metadata={
                    "query_time": datetime.now().isoformat(),
                    "repository_path": self.repo_path,
                    "git_command": " ".join(cmd)
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Git commit history query failed: {str(e)}"
            )
    
    def _format_time_for_git(self, time_str: str) -> str:
        """Format time string for git commands."""
        if not time_str:
            return ""
        
        # Handle relative times like "1h", "2d", "1w"
        if time_str.endswith(('h', 'd', 'w', 'm')):
            return time_str
        
        # Handle ISO format - git accepts it directly
        try:
            # Validate it's a proper datetime
            datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            return time_str
        except ValueError:
            # If parsing fails, assume it's already in git format
            return time_str
    
    async def _run_git_command(self, cmd: List[str]) -> str:
        """Run git command and return output."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.repo_path
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"Git command failed: {stderr.decode()}")
        
        return stdout.decode()
    
    async def _parse_git_log_output(self, output: str, include_diff: bool) -> List[Dict]:
        """Parse git log output into structured format."""
        commits = []
        lines = output.strip().split('\n')
        
        current_commit = None
        in_commit_message = False
        
        for line in lines:
            if line.startswith('commit '):
                # New commit
                if current_commit:
                    commits.append(current_commit)
                
                current_commit = {
                    "hash": line.split()[1],
                    "short_hash": line.split()[1][:8],
                    "author": "",
                    "author_date": "",
                    "committer": "",
                    "commit_date": "",
                    "message": "",
                    "files_changed": []
                }
                in_commit_message = False
                
            elif current_commit and line.startswith('Author:'):
                current_commit["author"] = line.replace('Author:', '').strip()
                
            elif current_commit and line.startswith('AuthorDate:'):
                current_commit["author_date"] = line.replace('AuthorDate:', '').strip()
                
            elif current_commit and line.startswith('Commit:'):
                current_commit["committer"] = line.replace('Commit:', '').strip()
                
            elif current_commit and line.startswith('CommitDate:'):
                current_commit["commit_date"] = line.replace('CommitDate:', '').strip()
                
            elif current_commit and line.strip() == '':
                # Empty line usually indicates start of commit message
                in_commit_message = True
                
            elif current_commit and in_commit_message and line.startswith('    '):
                # Commit message line (indented)
                current_commit["message"] += line.strip() + " "
        
        # Add the last commit
        if current_commit:
            commits.append(current_commit)
        
        # Get file changes for each commit if requested
        if include_diff:
            for commit in commits:
                commit["files_changed"] = await self._get_commit_files(commit["hash"])
        
        return commits
    
    async def _get_commit_files(self, commit_hash: str) -> List[Dict]:
        """Get files changed in a specific commit."""
        try:
            cmd = ["git", "show", "--name-status", "--format=", commit_hash]
            output = await self._run_git_command(cmd)
            
            files = []
            for line in output.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t', 1)
                    if len(parts) == 2:
                        status, filename = parts
                        files.append({
                            "status": status,
                            "filename": filename,
                            "change_type": self._get_change_type(status)
                        })
            
            return files
        except Exception:
            return []
    
    def _get_change_type(self, status: str) -> str:
        """Convert git status code to readable change type."""
        status_map = {
            'A': 'added',
            'M': 'modified', 
            'D': 'deleted',
            'R': 'renamed',
            'C': 'copied',
            'T': 'type_changed'
        }
        return status_map.get(status[0], 'unknown')
    
    async def _get_commit_stats(self, commits: List[Dict]) -> Dict:
        """Generate statistics from commits."""
        if not commits:
            return {}
        
        authors = {}
        commit_times = []
        
        for commit in commits:
            # Author statistics
            author = commit.get("author", "Unknown")
            authors[author] = authors.get(author, 0) + 1
            
            # Time analysis
            try:
                commit_date = commit.get("commit_date", "")
                if commit_date:
                    # Parse git date format
                    dt = datetime.strptime(commit_date.split()[0] + " " + commit_date.split()[1], "%Y-%m-%d %H:%M:%S")
                    commit_times.append(dt)
            except Exception:
                pass
        
        # Calculate time distribution
        time_distribution = {}
        if commit_times:
            now = datetime.now()
            for dt in commit_times:
                hours_ago = (now - dt).total_seconds() / 3600
                if hours_ago <= 1:
                    time_distribution["last_hour"] = time_distribution.get("last_hour", 0) + 1
                elif hours_ago <= 24:
                    time_distribution["last_24_hours"] = time_distribution.get("last_24_hours", 0) + 1
                elif hours_ago <= 168:  # 1 week
                    time_distribution["last_week"] = time_distribution.get("last_week", 0) + 1
                else:
                    time_distribution["older"] = time_distribution.get("older", 0) + 1
        
        return {
            "total_commits": len(commits),
            "unique_authors": len(authors),
            "authors": dict(sorted(authors.items(), key=lambda x: x[1], reverse=True)),
            "time_distribution": time_distribution,
            "most_recent_commit": commits[0] if commits else None,
            "oldest_commit": commits[-1] if commits else None
        }
    
    def _generate_summary(self, commits: List[Dict], stats: Dict) -> str:
        """Generate a human-readable summary of the commit history."""
        if not commits:
            return "No commits found in the specified time range."
        
        summary_parts = []
        
        # Basic stats
        summary_parts.append(f"Found {stats['total_commits']} commits by {stats['unique_authors']} authors")
        
        # Time distribution
        time_dist = stats.get('time_distribution', {})
        if time_dist:
            time_parts = []
            if time_dist.get('last_hour', 0) > 0:
                time_parts.append(f"{time_dist['last_hour']} in last hour")
            if time_dist.get('last_24_hours', 0) > 0:
                time_parts.append(f"{time_dist['last_24_hours']} in last 24h")
            if time_dist.get('last_week', 0) > 0:
                time_parts.append(f"{time_dist['last_week']} in last week")
            
            if time_parts:
                summary_parts.append(f"Distribution: {', '.join(time_parts)}")
        
        # Top authors
        authors = stats.get('authors', {})
        if authors:
            top_author = list(authors.items())[0]
            summary_parts.append(f"Most active: {top_author[0]} ({top_author[1]} commits)")
        
        # Most recent commit
        if commits:
            recent = commits[0]
            summary_parts.append(f"Latest: {recent['short_hash']} by {recent['author']}")
        
        return ". ".join(summary_parts) + "."


class GitDeploymentAnalysisTool(BaseTool):
    """Tool for analyzing recent deployments and releases from git history."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.repo_path = self.config.get("repo_path", ".")
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="git_deployment_analysis",
            name="Git Deployment Analysis",
            description="Analyze recent deployments, releases, and merge patterns to correlate with production issues.",
            inputs={
                "since": "string - Time range to analyze (e.g., '1h', '2d', '1w') (default: 48h)",
                "deployment_patterns": "list - Patterns that indicate deployments (default: ['deploy', 'release', 'merge'])",
                "include_merges": "boolean - Include merge commits (default: true)",
                "analyze_frequency": "boolean - Analyze deployment frequency (default: true)"
            },
            category="code"
        )
    
    def _validate_config(self) -> None:
        """Validate Git tool configuration."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.repo_path
            )
            if result.returncode != 0:
                raise RuntimeError(f"Directory {self.repo_path} is not a git repository")
        except Exception as e:
            raise RuntimeError(f"Git validation failed: {e}")
    
    async def execute(self, inputs: Dict[str, Any]) -> ToolResult:
        """Execute deployment analysis."""
        try:
            self.validate_inputs(inputs)
            
            since = inputs.get("since", "48h")
            deployment_patterns = inputs.get("deployment_patterns", ["deploy", "release", "merge"])
            include_merges = inputs.get("include_merges", True)
            analyze_frequency = inputs.get("analyze_frequency", True)
            
            # Get recent commits
            cmd = ["git", "log", "--oneline", "--date=iso", "--format=fuller", f"--since={since}"]
            if include_merges:
                cmd.append("--merges")
            
            output = await self._run_git_command(cmd)
            commits = await self._parse_commits_for_deployments(output, deployment_patterns)
            
            # Analyze deployment patterns
            analysis = {
                "time_range": since,
                "total_commits": len(commits),
                "deployment_commits": [c for c in commits if c.get("is_deployment")],
                "merge_commits": [c for c in commits if c.get("is_merge")],
                "patterns_found": deployment_patterns
            }
            
            if analyze_frequency:
                analysis["frequency_analysis"] = await self._analyze_deployment_frequency(commits)
            
            analysis["risk_assessment"] = self._assess_deployment_risk(analysis)
            
            return ToolResult(
                success=True,
                data=analysis,
                metadata={
                    "query_time": datetime.now().isoformat(),
                    "repository_path": self.repo_path
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"Git deployment analysis failed: {str(e)}"
            )
    
    async def _run_git_command(self, cmd: List[str]) -> str:
        """Run git command and return output."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.repo_path
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"Git command failed: {stderr.decode()}")
        
        return stdout.decode()
    
    async def _parse_commits_for_deployments(self, output: str, patterns: List[str]) -> List[Dict]:
        """Parse git output and identify deployment-related commits."""
        commits = []
        lines = output.strip().split('\n')
        
        for line in lines:
            if line.startswith('commit '):
                commit_hash = line.split()[1]
                commits.append({
                    "hash": commit_hash,
                    "short_hash": commit_hash[:8],
                    "message": "",
                    "is_deployment": False,
                    "is_merge": False,
                    "author": "",
                    "date": ""
                })
            elif commits and line.strip() and line.startswith('    '):
                # Commit message
                message = line.strip()
                commits[-1]["message"] += message + " "
                
                # Check for deployment patterns
                for pattern in patterns:
                    if pattern.lower() in message.lower():
                        commits[-1]["is_deployment"] = True
                        break
                
                # Check if it's a merge
                if "merge" in message.lower():
                    commits[-1]["is_merge"] = True
        
        return commits
    
    async def _analyze_deployment_frequency(self, commits: List[Dict]) -> Dict:
        """Analyze deployment frequency patterns."""
        deployment_commits = [c for c in commits if c.get("is_deployment")]
        
        if len(deployment_commits) < 2:
            return {"frequency": "insufficient_data"}
        
        # Calculate time between deployments
        # This is a simplified analysis - in real implementation you'd parse actual dates
        frequency_analysis = {
            "deployment_count": len(deployment_commits),
            "total_commits": len(commits),
            "deployment_ratio": len(deployment_commits) / len(commits) if commits else 0,
            "pattern": "normal"  # Could be enhanced with actual time analysis
        }
        
        # Assess frequency
        if frequency_analysis["deployment_ratio"] > 0.5:
            frequency_analysis["pattern"] = "high_frequency"
        elif frequency_analysis["deployment_ratio"] > 0.2:
            frequency_analysis["pattern"] = "moderate_frequency"
        else:
            frequency_analysis["pattern"] = "low_frequency"
        
        return frequency_analysis
    
    def _assess_deployment_risk(self, analysis: Dict) -> Dict:
        """Assess risk based on deployment patterns."""
        risk_factors = []
        risk_level = "low"
        
        deployment_commits = analysis.get("deployment_commits", [])
        total_commits = analysis.get("total_commits", 0)
        
        # High deployment frequency risk
        if len(deployment_commits) > 5:
            risk_factors.append("High deployment frequency detected")
            risk_level = "medium"
        
        # Recent deployments risk
        if len(deployment_commits) > 0:
            risk_factors.append("Recent deployments found - potential correlation with issues")
        
        # Multiple deployments risk
        if len(deployment_commits) > 3:
            risk_factors.append("Multiple recent deployments - increased change risk")
            risk_level = "high"
        
        return {
            "level": risk_level,
            "factors": risk_factors,
            "recommendation": self._get_risk_recommendation(risk_level, len(deployment_commits))
        }
    
    def _get_risk_recommendation(self, risk_level: str, deployment_count: int) -> str:
        """Get recommendation based on risk assessment."""
        if risk_level == "high":
            return "High deployment activity detected. Consider investigating recent changes for correlation with production issues."
        elif risk_level == "medium":
            return "Moderate deployment activity. Review recent deployments if issues coincide with deployment times."
        else:
            return "Low deployment risk. Recent code changes less likely to be the primary cause." 