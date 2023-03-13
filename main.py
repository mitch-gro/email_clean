import argparse
import base64
import json
import os.path
import re
import subprocess

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://mail.google.com/"]
PULL_REQUEST_REGEX = re.compile(r"https:\/\/github\.com\/.*\/pull\/\d+")
REPO_REGEX = re.compile(r"https:\/\/github\.com\/.*\/pull\/\d+")
OWNER = "gro-intelligence"


def yes_no_prompt(prompt):
    while True:
        response = input(prompt + " [y/n]: ")
        if response.lower() == "y":
            return True
        elif response.lower() == "n":
            return False
        else:
            print('Invalid response. Please enter "y" or "n".')


class GmailHandler:
    def __init__(self, creds, github_handler, user_id="me"):
        self.service = build("gmail", "v1", credentials=creds)
        self.user_id = user_id
        self.github_handler = github_handler

    def _get_messages(self, query=""):
        results = []
        page_token = None
        print("Fetching messages...")
        while True:
            # Make a request with the page_token parameter
            response = (
                self.service.users()
                .threads()
                .list(userId=self.user_id, q=query, pageToken=page_token)
                .execute()
            )

            # Get the threads from the response and add them to the results list
            threads = response.get("threads", [])
            results.extend(threads)

            # Check if there are more results
            if "nextPageToken" in response:
                # If there are more results, update the page_token and make another request
                page_token = response["nextPageToken"]
            else:
                # If there are no more results, break out of the loop
                break
        print("Got messages")

        return results

    def _delete_message(self, thread_id):
        self.service.users().threads().delete(
            userId=self.user_id, id=thread_id
        ).execute()

    def _get_full_thread(self, thread_id):
        return (
            self.service.users()
            .threads()
            .get(userId=self.user_id, id=thread_id, format="full")
            .execute()
            .get("messages", [])
        )

    def _decode_message_part(self, part):
        if part["mimeType"] == "text/plain":
            message_body = part["body"]["data"].replace("-", "+").replace("_", "/")
            return str(base64.b64decode(message_body))

        return None

    def _search_for_regex(self, text, regex):
        return regex.search(text)

    def _get_pull_request_metadata_from_thread(self, thread_id):
        pull_request_url = None
        for message in self._get_full_thread(thread_id):
            subject = [
                x for x in message["payload"]["headers"] if x["name"] == "Subject"
            ][0]["value"]
            sender = [
                x
                for x in message["payload"]["headers"]
                if x["name"] == "X-GitHub-Sender"
            ][0]["value"]

            if re.search(r"\[gro-intelligence/gro\]", subject):
                message_parts = message["payload"].get("parts")

                if not message_parts:
                    continue

                for part in message_parts:
                    decoded_message_part = self._decode_message_part(part)
                    if decoded_message_part:
                        if pull_request_url_match := self._search_for_regex(
                            decoded_message_part, PULL_REQUEST_REGEX
                        ):
                            pull_request_url = pull_request_url_match.group(0).split(
                                "#"
                            )[0]
                            break

        if pull_request_url:
            return {
                "url": pull_request_url,
                "snippet": message["snippet"],
                "subject": subject,
                "sender": sender,
            }
        else:
            return {}

    def _extract_pr_number(self, pull_request_url):
        # Define a regular expression pattern to match the pull request number
        pull_request_pattern = r"/pull/(\d+)"
        if match := re.search(pull_request_pattern, pull_request_url):
            # Extract the pull request number from the match object
            return match.group(1)

    def prune_messages(self, query=""):
        threads = self._get_messages(query)

        for thread in threads:
            thread_id = thread["id"]
            metadata = self._get_pull_request_metadata_from_thread(thread_id)
            pull_request_url = metadata.get("url")
            if pull_request_url:
                pr_number = pull_request_url.split("/")[-1]
                repo_name = pull_request_url.split("/")[-3]

                if not self.github_handler.is_assignee(repo_name, pr_number):
                    # self.github_handler.unsubscribe_from_thread(
                    #     repo_name,
                    #     pr_number,
                    # )
                    if yes_no_prompt(
                        f"Delete message from '{metadata.get('sender')}' with subject '{metadata.get('subject')}'?"
                    ):
                        self._delete_message(thread_id)


class GithubHandler:
    def __init__(self):
        self.username = os.getenv("GITHUB_USERNAME")
        self.access_token = os.getenv("GITHUB_ACCESS_TOKEN")

        if not self.username:
            raise ValueError("Github username is required")

        if not self.access_token:
            raise ValueError("Github access token is required")

    def is_assignee(self, repo, pull_request_number):
        # Run the gh pr view command and capture its output
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pull_request_number),
                "--json",
                "assignees",
                "-R",
                f"{OWNER}/{repo}",
            ],
            stdout=subprocess.PIPE,
        )

        # Extract the JSON output from the command's stdout
        json_output = result.stdout.decode("utf-8")

        # Parse the JSON output into a Python object
        return self.username in [
            assignee.get("login")
            for assignee in json.loads(json_output).get("assignees")
        ]

    def _get_thread_id(self, repo, pull_request_number):
        # TODO
        pass

    def unsubscribe_from_thread(self, repo, pull_request_number):
        # Can't yet unsubscribe from a thread because it requires admin
        # permissions on the Gro repo
        # TODO fix
        thread_id = self._get_thread_id(repo, pull_request_number)
        # Make a request to the GitHub API to get the pull request details

        # Define the API endpoint for unsubscribing from a pull request
        url = f"https://api.github.com/notifications/threads/{thread_id}/subscription"
        breakpoint()
        # Make a DELETE request to the API endpoint with your GitHub access token
        response = requests.put(
            url,
            headers={"Authorization": f"token {self.access_token}"},
            params=json.dumps({"ignored": True}),
        )

        # Check the status code of the response
        if response.status_code == 204:
            print("Unsubscribed from pull request successfully!")
        else:
            print(
                f"Failed to unsubscribe from pull request with status code {response.status_code}"
            )


def get_gmail_credentials():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing credentials.")
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    print("Got credentials.")
    return creds


def main():
    github_handler = GithubHandler()
    creds = get_gmail_credentials()
    gmail_handler = GmailHandler(creds, github_handler)
    gmail_handler.prune_messages(query="in:inbox from:notifications@github.com")


if __name__ == "__main__":
    main()
