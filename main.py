#!/usr/bin/env python3
import os
import subprocess
import sys
import json
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GIT_USERNAME = os.environ.get("GIT_USERNAME", "github-actions")
GIT_EMAIL = os.environ.get("GIT_EMAIL", "github-actions@users.noreply.github.com")
BASE_BRANCH = os.environ.get("BASE_BRANCH", "main")
COMBINE_BRANCH = os.environ.get("COMBINE_BRANCH", "combine-dependabot")
PR_USER = os.environ.get("PR_USER", "dependabot[bot]")
REPO = os.environ.get("GITHUB_REPOSITORY")
OUTPUT_JSON = os.environ.get("OUTPUT_JSON", "")

def run_git(*args, check=True):
    try:
        result = subprocess.run(["git"] + list(args), check=check, text=True, capture_output=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"error executing git {' '.join(args)}: {e.stderr.strip()}")

def auth_git():
    try:
        run_git("config", "--global", "user.name", GIT_USERNAME)
        run_git("config", "--global", "user.email", GIT_EMAIL)
        logger.info("git authentication configured")
        return True
    except RuntimeError:
        logger.warning("failed to set git config")
    except Exception as e:
        logger.error(f"unexpected error: {str(e)}")
    return False

def config_git():
    try:
        run_git("config", "--global", "push.autoSetupRemote", "always")
        logger.info("git config set for autoSetupRemote always.")
        return True
    except RuntimeError:
        logger.warning("failed to set git config")
    except Exception as e:
        logger.error(f"unexpected error: {str(e)}")
    return False

def branch_exists_remote(branch_name):
    try:
        output = run_git("ls-remote", "--heads", "origin", branch_name)
        return bool(output)
    except subprocess.CalledProcessError:
        return False

def setup_repository():
    logger.info(f"setting up branch '{COMBINE_BRANCH}' based on '{BASE_BRANCH}'...")
    try:
        run_git("fetch", "--all")
        if branch_exists_remote(COMBINE_BRANCH):
            logger.info(f"remote branch '{COMBINE_BRANCH}' already exists. Checking it out.")
            run_git("checkout", COMBINE_BRANCH)
            run_git("reset", "--hard", f"origin/{COMBINE_BRANCH}")
            return True
        run_git("checkout", "-B", COMBINE_BRANCH, BASE_BRANCH)
    except RuntimeError as e:
        raise RuntimeError(f"error creating or switching to branch '{COMBINE_BRANCH}': {e}")
    except Exception as e:
        raise RuntimeError(f"unexpected error: {str(e)}")
    return True

def get_dependabot_prs() -> list:
    logger.info(f"fetching open PRs based on '{BASE_BRANCH}' with head starting with '{PR_USER}'...")
    owner, repo = REPO.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open&base={BASE_BRANCH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    pulls = response.json()
    
    return [
        pr for pr in pulls if pr["user"]["login"] == PR_USER
    ]

def commit_already_applied(commit_sha) -> bool:
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", commit_sha, "HEAD"], check=True)
        logger.info(f"commit {commit_sha} is already present in the branch.")
        return True
    except subprocess.CalledProcessError:
        return False

def get_commit_diff(commit_sha) -> str:
    diff = run_git("diff", f"{commit_sha}^!", check=False)
    return diff.strip()

def cherry_pick_pr(pr) -> bool:
    commit_sha = pr["head"]["sha"]
    pr_number = pr["number"]
    logger.info(f"cherry-picking commit {commit_sha} from PR #{pr_number}...")
    try:
        subprocess.run([
            "git", "cherry-pick", "--strategy=recursive", "-X", "theirs",
            "--empty=drop", commit_sha
        ], check=True)
        logger.info(f"cherry-pick completed for commit {commit_sha}")
        return True
    except subprocess.CalledProcessError:
        logger.warning(f"conflict detected for PR #{pr_number}, skipping commit...")
        subprocess.run(["git", "cherry-pick", "--skip"], check=False)
        return False

def has_changes() -> bool:
    status = run_git("status", "--porcelain")
    if status.strip():
        return True
    
    try:
        upstream = run_git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    except RuntimeError:
        return True
    
    ahead = run_git("rev-list", "--count", "--left-only", f"{upstream}...HEAD")
    return int(ahead.strip()) > 0

def push_branch() -> bool:
    if not has_changes():
        logger.info("no changes to push. Skipping push.")
        return False
    logger.info(f"pushing branch '{COMBINE_BRANCH}' to origin...")
    run_git("push", "-u", "origin", COMBINE_BRANCH, "--force")
    return True

def create_pull_request(pr_list_text):
    if not pr_list_text:
        logger.info("no PRs found to combine. No new PR will be created.")
        return
    owner, repo = REPO.split("/")
    title = f"Combine Pull Requests from {PR_USER}"
    body = f"This pull request was automatically created by combining the following Dependabot PRs:\n\n{pr_list_text}"
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "title": title,
        "head": COMBINE_BRANCH,
        "base": BASE_BRANCH,
        "body": body
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))
    response.raise_for_status()
    pr = response.json()

    logger.info(f"pull request created: {pr.get('html_url')}")
    return pr

def main():
    auth_git()
    #if not config_git():
    #    logger.error("failed to configure git. Exiting.")
    #    return
    setup_repository()

    prs = get_dependabot_prs()
    if not prs:
        logger.info("no Dependabot PRs found to combine.")
        return

    pr_list_text = ""
    combined_prs = []
    failed_prs = []
    omitted_prs = []

    for pr in prs:
        logger.info(f"Processing PR #{pr['number']} - {pr['title']}")
        if commit_already_applied(pr["head"]["sha"]) or not get_commit_diff(pr["head"]["sha"]):
            logger.info(f"pr #{pr['number']} has already been applied or has no effective changes. Skipping.")
            omitted_prs.append({
                "number": pr["number"], "title": pr["title"], "url": pr["html_url"]})
            continue
    
        if cherry_pick_pr(pr):
            combined_prs.append({
                "number": pr["number"], "title": pr["title"], "url": pr["html_url"]})
            pr_list_text += f"- #{pr['number']}\n" #{pr['title']} ({pr['html_url']})\n"
            continue
    
        failed_prs.append({
            "number": pr["number"], "title": pr["title"], "url": pr["html_url"]})

    if push_branch():
        pr_combine = create_pull_request(pr_list_text)
    else:
        logger.info("no real changes were made. No new PR was created.")

    if OUTPUT_JSON:
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump({
                "combined_prs": combined_prs,
                "failed_prs": failed_prs,
                "omitted_prs": omitted_prs,
                "pr_combine": pr_combine,
                "branch": COMBINE_BRANCH,
                "base": BASE_BRANCH
            }, f, indent=2)
        logger.info(f"result saved to {OUTPUT_JSON}")

if __name__ == "__main__":
    if not GITHUB_TOKEN or not REPO:
        logger.error("error: Ensure that GITHUB_TOKEN and GITHUB_REPOSITORY are defined.")
        sys.exit(1)

    try:
        main()
    except Exception as e:
        logger.exception("error during PR combination: %s", str(e))
        sys.exit(1)
