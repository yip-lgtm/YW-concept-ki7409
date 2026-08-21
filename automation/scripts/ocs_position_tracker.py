# Auto-detect repo path: GHA runner uses $GITHUB_WORKSPACE, local uses /workspace
if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")