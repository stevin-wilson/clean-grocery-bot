# Getting Started

This guide walks you through deploying your own **clean-grocery-bot** from scratch. If you have never used AWS or Telegram before, you are in the right place — every step is explained from the beginning.

By the end of this guide, you will have a private Telegram bot that searches for clean grocery products on your behalf, filters out seed oils and artificial additives, and uses AI to rank the results.

**Estimated time:** 45–90 minutes.

---

## Before You Begin: Values to Collect

As you work through the steps, you will generate several values that you need later. Keep this table handy — fill it in as you go.

| Value                  | Where you get it                     | Your value |
| ---------------------- | ------------------------------------ | ---------- |
| Telegram bot token     | Step 1.2 — BotFather                 |            |
| Telegram chat ID       | Step 2                               |            |
| Webhook secret         | Step 10 — generated on your computer |            |
| API Gateway invoke URL | Step 9                               |            |
| AWS region             | Step 4.2 — you choose                |            |

---

## Step 0: Prerequisites

### What You Need

- A computer running Windows, macOS, or Linux
- A **Telegram account** — free, takes 2 minutes to create
- An **AWS account**
- The following software, installed in Steps 3 and 4:
  - Git
  - Python 3.12 or newer
  - `uv` (a Python package manager)
  - AWS CLI v2

You do not need any programming experience to follow this guide.

---

## Step 1: Set Up Your Telegram Bot

!!! note "What is Telegram?"
Telegram is a free messaging app, similar to WhatsApp or iMessage. Your grocery bot will live inside Telegram — you send it a message, and it sends back product recommendations.

!!! note "What is BotFather?"
BotFather is Telegram's official tool for creating and managing bots. It is itself a bot — you interact with it by sending it commands.

### 1.1 Install Telegram and Create an Account

1. Download Telegram from [https://telegram.org](https://telegram.org) and install it on your phone or computer.
2. Create a free account using your phone number.
3. Verify your phone number when prompted.

### 1.2 Create a New Bot with BotFather

1. Open Telegram and search for **@BotFather** (look for the blue verified checkmark).
2. Start a conversation with BotFather by tapping or clicking **Start**.
3. Send the message `/newbot`.
4. BotFather will ask for a **display name** — the friendly name people see. Example: `Clean Grocery Bot`.
5. BotFather will then ask for a **username** — this must end in `bot`. For privacy, choose something non-obvious rather than something predictable. Example: `cgb_xk7r2_bot` rather than `cleangrocerybot`.

   !!! warning "Choose a non-obvious username"
   Anyone who knows your bot's username can message it. A random-looking username like `cgb_xk7r2_bot` is effectively undiscoverable by strangers. You will still be able to find your own bot by searching for its exact username.

6. BotFather will reply with your **bot token**. It looks like this:

   ```
   123456789:ABCDEFghijklmnopqrstuvwxyz1234567890
   ```

7. **Save this token now.** Copy it into the "Values to Collect" table above. You will need it in Steps 11 and 14.

   !!! warning "Treat the bot token like a password"
   Anyone with your bot token can send messages as your bot and read messages sent to it. Never share it publicly, never commit it to a code repository.

### 1.3 Configure Bot Privacy

Still in the BotFather conversation:

**Disable group access:**

1. Send `/setjoingroups`.
2. BotFather will list your bots — select your new bot.
3. Choose **Disable**.

**Enable privacy mode:**

1. Send `/setprivacy`.
2. Select your bot.
3. Choose **Enable**.

!!! note "Why do this?"
These two settings prevent your bot from being added to Telegram group chats and prevent strangers from interacting with it in groups. Your bot is a private personal tool — not a public service.

---

## Step 2: Find Your Telegram Chat ID

The bot uses your **chat ID** to know which Telegram users are allowed to talk to it. Every Telegram user has a unique numeric ID.

**Option A — Using @userinfobot (easiest):**

1. In Telegram, search for **@userinfobot**.
2. Start a conversation with it by tapping **Start**.
3. It will immediately reply with your user information, including a field called **Id**. That number is your chat ID.

**Option B — Using the Telegram API directly:**

1. First, start a conversation with your own bot (search for its username and press Start).
2. In a web browser, open this URL — replace `YOUR_BOT_TOKEN` with your actual token:

   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```

3. You will see JSON output. Look for `"chat": {"id": 123456789}` — that number is your chat ID.

**Save your chat ID** in the "Values to Collect" table. It will be a plain integer (for example: `987654321`).

---

## Step 3: Install Local Tools

!!! note "What is a terminal?"
A terminal (also called a command prompt or shell) lets you type commands to your computer. On Windows, search for "Command Prompt" or "PowerShell". On macOS, search for "Terminal". On Linux, you likely already know where it is.

### 3.1 Install Git

Git is used to download the bot's source code from GitHub.

- **Windows:** Download from [https://git-scm.com/download/win](https://git-scm.com/download/win) and run the installer. During installation, accept all defaults.
- **macOS:** Run `git --version` in your terminal — macOS will prompt you to install it automatically if it is missing.
- **Linux (Ubuntu/Debian):** `sudo apt install git`

Verify the installation:

```bash
git --version
```

You should see something like `git version 2.43.0`.

### 3.2 Install Python 3.12+

- **Windows/macOS:** Download from [https://www.python.org/downloads/](https://www.python.org/downloads/). Install Python 3.12 or newer. On Windows, check the box **"Add Python to PATH"** during installation.
- **Linux:** `sudo apt install python3.12` (or use your distribution's package manager).

Verify:

```bash
python3 --version
```

You need `Python 3.12.x` or higher.

### 3.3 Install uv

`uv` is a fast Python package manager used by this project.

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows (PowerShell)"

    ```powershell
    irm https://astral.sh/uv/install.ps1 | iex
    ```

=== "Any platform (via pip)"

    ```bash
    pip install uv
    ```

Verify:

```bash
uv --version
```

### 3.4 Install AWS CLI v2

The AWS CLI lets you interact with AWS services from your terminal.

- **macOS / Windows:** Download the installer from the [AWS CLI installation page](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
- **Linux:**

  ```bash
  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip awscliv2.zip
  sudo ./aws/install
  ```

Verify:

```bash
aws --version
```

You should see `aws-cli/2.x.x`.

---

## Step 4: Configure the AWS CLI

!!! note "What is an IAM user?"
IAM stands for Identity and Access Management. AWS has a "root" account (the email and password you used to sign up) and separate IAM users that you create for specific purposes. AWS strongly recommends not using your root account for everyday tasks.

### 4.1 Create an IAM User

!!! warning "Do not use your root account credentials"
Your root account has unlimited access to everything in your AWS account. If its credentials were ever exposed, the damage could be severe. Always use a dedicated IAM user.

1. Sign in to the [AWS Management Console](https://console.aws.amazon.com).
2. In the search bar at the top, type **IAM** and open the IAM service.
3. In the left sidebar, click **Users**.
4. Click **Create user**.
5. Choose a username, for example `clean-grocery-bot-admin`. Click **Next**.
6. Select **Attach policies directly**.
7. Search for and select **AdministratorAccess**. Click **Next**, then **Create user**.

**Create access keys for CLI use:**

1. Click on your new user's name.
2. Click the **Security credentials** tab.
3. Scroll to **Access keys** and click **Create access key**.
4. Select **Command Line Interface (CLI)** as the use case.
5. Acknowledge the recommendation and click **Next**.
6. Click **Create access key**.
7. **Copy both the Access Key ID and the Secret Access Key now.** You cannot retrieve the secret key again after leaving this page.

!!! note "AdministratorAccess is for setup only"
AdministratorAccess is a broad permission set. It is used here because you need to create multiple AWS resources during setup. The bot itself uses a separate, tightly scoped IAM role (created in Step 7) with only the minimum permissions it needs to run.

### 4.2 Run aws configure

In your terminal:

```bash
aws configure
```

You will be prompted for four values:

| Prompt                | What to enter                             |
| --------------------- | ----------------------------------------- |
| AWS Access Key ID     | The access key ID you just copied         |
| AWS Secret Access Key | The secret access key you just copied     |
| Default region name   | `us-east-2` (recommended — see tip below) |
| Default output format | `json`                                    |

!!! tip "Why us-east-2?"
AWS Bedrock (the AI service this bot uses) supports Claude Haiku 4.5 in `us-east-2`. Not all AWS regions support all Bedrock models. Using `us-east-2` avoids compatibility issues.

Verify the configuration works:

```bash
aws sts get-caller-identity
```

You should see JSON showing your account ID and the IAM user name you just created.

---

## Step 5: Set Up Billing Protection

!!! warning "Do this before any other AWS step that costs money"
AWS charges by usage. A billing alarm sends you an email the moment your monthly charges exceed a threshold, so you can catch unexpected costs early. This bot is designed to cost less than $1/month for family use, but it is good practice to set this up first.

!!! note "What is CloudWatch?"
CloudWatch is AWS's monitoring and alerting service. It can watch metrics — like your monthly AWS bill — and send you a notification when they exceed a threshold you define.

1. In the AWS Console search bar, type **CloudWatch** and open the service.
2. Make sure you are in **us-east-1** (check the region selector in the top-right corner of the console). AWS billing metrics are only available in us-east-1 — switch to it just for this step.
3. In the left sidebar, click **Alarms**, then **All alarms**.
4. Click **Create alarm**.
5. Click **Select metric**.
6. Choose **Billing** → **Total Estimated Charge** → check the box next to **USD** → click **Select metric**.
7. Under **Conditions**, set:
   - Threshold type: **Static**
   - Whenever EstimatedCharges is: **Greater than**
   - Value: `5`
8. Click **Next**.
9. Under **Notification**, click **Create new topic**.
   - Topic name: `billing-alert`
   - Enter your email address.
   - Click **Create topic**.
10. Click **Next**, name the alarm `monthly-billing-5-dollar-alert`, click **Next**, then **Create alarm**.
11. **Check your email** and click the confirmation link in the message from AWS. The alarm will not send notifications until you confirm.

---

## Step 6: Verify AWS Bedrock Access

!!! note "What is AWS Bedrock?"
AWS Bedrock is a service that gives you access to AI models through an API. This bot uses **Amazon Nova 2 Lite** — a fast, affordable Amazon model — to score and rank products by ingredient cleanliness.

!!! note "Model access in 2025+"
AWS retired the manual model-access page. Models are now automatically available when first invoked. You no longer need to tick a box — skip straight to Step 7.

!!! warning "If you want to use an Anthropic model (Claude) instead"
Anthropic models require a one-time **use case details form** before first use. If you skip this, Lambda will return `ResourceNotFoundException: Model use case details have not been submitted`. To submit the form:

    1. Open the [Bedrock Model Catalog](https://us-east-2.console.aws.amazon.com/bedrock/home?region=us-east-2#/models) in us-east-2.
    2. Search for the Claude model you want and click on it.
    3. Look for a **"Submit use case details"** button or banner and complete the form.
    4. Wait 15 minutes before invoking the model.

    After submitting, also update the `BEDROCK_MODEL_ID` Lambda environment variable and IAM policy as described in the Troubleshooting section below.

!!! note "What is an inference profile?"
Newer Bedrock models (Nova 2 Lite, Claude Haiku 4.5, etc.) do not support simple on-demand invocation by bare model ID. They require an **inference profile** — a routing layer that spreads requests across multiple AWS regions for higher availability. The profile ID is the same as the model ID but prefixed with `us.` (e.g. `us.amazon.nova-2-lite-v1:0`). Always use the `us.` prefix for newer models.

---

## Step 7: Create the IAM Role for Lambda

!!! note "What is an IAM role?"
An IAM role is a set of permissions that an AWS service assumes when doing work on your behalf. Your Lambda function needs a role so AWS knows exactly what it is allowed to do: call the AI model, read your secrets, and write logs. Nothing more.

1. In the AWS Console, open **IAM**.
2. In the left sidebar, click **Roles**.
3. Click **Create role**.
4. Under **Trusted entity type**, select **AWS service**.
5. Under **Use case**, select **Lambda**. Click **Next**.
6. On the permissions page, click **Next** without selecting any managed policies. You will add a precise inline policy instead.
7. Name the role `clean-grocery-bot-role`. Click **Create role**.

**Add the inline policy:**

1. Click on the `clean-grocery-bot-role` you just created.
2. Under the **Permissions** tab, click **Add permissions** → **Create inline policy**.
3. Click the **JSON** tab and replace all existing content with:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "bedrock:InvokeModel",
         "Resource": [
           "arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0",
           "arn:aws:bedrock:*:*:inference-profile/us.amazon.nova-2-lite-v1:0"
         ]
       },
       {
         "Effect": "Allow",
         "Action": "ssm:GetParameter",
         "Resource": "arn:aws:ssm:*:*:parameter/clean-grocery-bot/*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "logs:CreateLogGroup",
           "logs:CreateLogStream",
           "logs:PutLogEvents"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

   !!! note "Why two Resource ARNs for Bedrock?"
   Newer models require invocation via an **inference profile** (`inference-profile/us.…`), not the bare foundation model ID. Both ARNs must be present: one is used by Lambda at runtime, and the other covers any direct API calls you make during development.

4. Click **Next**. Name the policy `clean-grocery-bot-inline-policy`. Click **Create policy**.

---

## Step 8: Create the Lambda Function

!!! note "What is AWS Lambda?"
Lambda is a "serverless" compute service. You give it your code, and AWS runs it on demand — only when someone sends a message to your bot. You pay only for the time the code actually runs, which for a personal bot costs fractions of a cent per month.

1. In the AWS Console, search for **Lambda** and open the service.
2. Click **Create function**.
3. Select **Author from scratch**.
4. Fill in:
   - **Function name:** `clean-grocery-bot`
   - **Runtime:** Python 3.12
   - **Architecture:** match your build machine — `arm64` for Apple Silicon (M1/M2/M3) or Windows ARM devices; `x86_64` for Intel/AMD machines. The `deploy.sh` script detects this automatically and sets it on every deploy, so this initial choice is just the starting value.
5. Under **Permissions**, expand **Change default execution role**.
6. Select **Use an existing role**.
7. Choose `clean-grocery-bot-role` from the dropdown.
8. Click **Create function**.

**Set the timeout:**

1. Click the **Configuration** tab.
2. Click **General configuration** → **Edit**.
3. Change **Timeout** to `0 min 30 sec`.
4. Click **Save**.

**Set the concurrency limit:**

1. Still in **Configuration**, click **Concurrency**.
2. Click **Edit**.
3. Select **Reserve concurrency** and enter `5`.
4. Click **Save**.

!!! note "Why limit concurrency to 5?"
This is a cost protection measure. Even if someone sends many messages at once, at most 5 instances of the bot will run simultaneously. Combined with API Gateway throttling (Step 9), this makes it practically impossible for unexpected usage to cause a large bill.

!!! warning "If you get \"The unreserved account concurrency can't go below 10\""
New AWS accounts often have a default concurrent execution limit of 10. AWS requires at least 10 units to remain unreserved, so setting any reserved concurrency on such an account fails. **Option A — Skip this step for now.** The API Gateway throttling in Step 9 (rate 10, burst 20) already provides meaningful cost protection — you can revisit this setting later. **Option B — Request a limit increase:** open **Service Quotas** → **AWS Lambda** → search for **Concurrent executions** → **Request quota increase** and request at least 25. Increases are usually approved within a few minutes.

!!! tip "Leave environment variables empty"
Your secrets will be stored in Parameter Store (Step 11) — not here. This is more secure because Parameter Store values are encrypted at rest and only the specific IAM role can read them.

**Note:** You will set the handler after deploying the code in Step 13.

---

## Step 9: Create the API Gateway

!!! note "What is API Gateway?"
API Gateway gives your Lambda function a public URL that Telegram can send messages to. When someone messages your bot, Telegram sends an HTTPS POST request to this URL, which triggers your Lambda function.

!!! note "What is a webhook?"
A webhook is a URL that a service calls automatically when something happens. Instead of constantly asking Telegram "any new messages?" (called polling), the bot registers a URL with Telegram and says "POST here whenever I receive a message." This is more efficient, faster, and costs less.

1. In the AWS Console, search for **API Gateway** and open the service.
2. Click **Create API**.
3. Under **HTTP API**, click **Build**.
4. Click **Add integration**.
5. Select **Lambda** as the integration type.
6. Select your region and choose the `clean-grocery-bot` Lambda function.
7. Click **Next**.
8. Under **Configure routes**, change the method to **POST** and the path to `/webhook`. Click **Next**.
9. Leave the stage name as `$default`. Click **Next**, then **Create**.

**Set throttling limits:**

1. On the API detail page, click the stage name **$default** in the left sidebar.
2. Click **Throttling** → **Edit** (you may need to enable the route-level throttling toggle first).
3. Set **Rate** to `10` and **Burst** to `20`.
4. Click **Save**.

**Copy the invoke URL:**

On the API detail page, find the **Invoke URL** — it looks like:

```
https://abc1234xyz.execute-api.us-east-2.amazonaws.com
```

Your webhook URL will be this URL with `/webhook` appended:

```
https://abc1234xyz.execute-api.us-east-2.amazonaws.com/webhook
```

Save the full webhook URL (including `/webhook`) in the "Values to Collect" table.

---

## Step 10: Generate a Webhook Secret

The webhook secret is a random string that Telegram includes with every request it sends to your API Gateway. Your Lambda function checks this string before doing anything else — if it does not match, the request is rejected immediately. This prevents anyone who discovers your API Gateway URL from sending fake requests to your bot.

Generate a secure random string in your terminal:

=== "macOS / Linux"

    ```bash
    openssl rand -hex 32
    ```

=== "Windows (PowerShell)"

    ```powershell
    -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
    ```

The output will be a 64-character string of letters and numbers, for example:

```
a3f8e2c1b5d4a7f0e9c2b8d6a1f5e3c7b9d2a4f6e8c0b3d5a7f9e1c4b6d8a2f0
```

**Save this string** in the "Values to Collect" table as your webhook secret.

---

## Step 11: Store Secrets in AWS Parameter Store

!!! note "What is AWS Parameter Store?"
Parameter Store is a secure place to store secrets in AWS. Unlike Lambda environment variables (which appear as plain text in the console), Parameter Store stores values encrypted. Only the specific IAM role you configured in Step 7 can read them.

Open your terminal and run each command below, replacing the placeholder values with your real ones.

**Secret 1 — Telegram bot token:**

```bash
aws ssm put-parameter \
    --name "/clean-grocery-bot/telegram-token" \
    --value "YOUR_BOT_TOKEN" \
    --type SecureString
```

Replace `YOUR_BOT_TOKEN` with the token from Step 1.2.

**Secret 2 — Webhook secret:**

```bash
aws ssm put-parameter \
    --name "/clean-grocery-bot/webhook-secret" \
    --value "YOUR_WEBHOOK_SECRET" \
    --type SecureString
```

Replace `YOUR_WEBHOOK_SECRET` with the string generated in Step 10.

**Secret 3 — Allowed chat IDs:**

```bash
aws ssm put-parameter \
    --name "/clean-grocery-bot/allowed-chat-ids" \
    --value "YOUR_CHAT_ID" \
    --type SecureString
```

Replace `YOUR_CHAT_ID` with the number from Step 2.

!!! tip "Adding multiple family members"
If you want more than one person to use the bot, provide a comma-separated list of chat IDs:
`bash
    aws ssm put-parameter \
        --name "/clean-grocery-bot/allowed-chat-ids" \
        --value "123456789,987654321" \
        --type SecureString
    `
Each family member needs to find their own chat ID using @userinfobot (Step 2).

**Summary of secrets stored:**

| Parameter Store path                  | Contains                                            |
| ------------------------------------- | --------------------------------------------------- |
| `/clean-grocery-bot/telegram-token`   | Telegram bot token from BotFather                   |
| `/clean-grocery-bot/webhook-secret`   | The random secret generated in Step 10              |
| `/clean-grocery-bot/allowed-chat-ids` | Your Telegram chat ID (comma-separated if multiple) |

---

## Step 12: Clone the Repo and Configure Preferences

**Download the code:**

```bash
git clone https://github.com/stevin-wilson/clean-grocery-bot.git
cd clean-grocery-bot
```

**Optional — customize dietary preferences:**

Open `dietary_preference_config.json` in a text editor (Notepad, TextEdit, VS Code, etc.). The defaults work well for most users — the bot will already avoid seed oils and artificial additives, prefer organic products, and return 3 recommendations per query.

Common things to change:

| What to change                | Where in the file                                  | Example value                    |
| ----------------------------- | -------------------------------------------------- | -------------------------------- |
| Your country                  | `"market"` → `"country"`                           | `"GB"` for UK, `"CA"` for Canada |
| Default number of results     | `"recommendations"` → `"default_count"`            | `5`                              |
| Ingredients to always exclude | `"dietary_restrictions"` → `"exclude_ingredients"` | `["gluten", "dairy"]`            |
| Response verbosity            | `"response"` → `"format"`                          | `"short"` or `"detailed"`        |

**Install project dependencies:**

```bash
uv sync --all-groups
```

---

## Step 13: Deploy the Lambda

This step packages your code and uploads it to your Lambda function in AWS.

```bash
export LAMBDA_FUNCTION_NAME=clean-grocery-bot
export AWS_REGION=us-east-2
bash deploy.sh
```

!!! tip "Windows users"
Windows Command Prompt does not support `export`. Use Git Bash (installed with Git for Windows) to run the commands above. Alternatively, in PowerShell:
`powershell
    $env:LAMBDA_FUNCTION_NAME = "clean-grocery-bot"
    $env:AWS_REGION = "us-east-2"
    bash deploy.sh
    `

The script will:

1. Export dependencies with `uv`
2. Install them into a `build/` directory using `uv pip install`
3. Auto-detect your machine architecture (`arm64` or `x86_64`) and set the Lambda architecture to match — this prevents native extension import errors (e.g. `pydantic_core`)
4. Zip the build directory and upload it to Lambda

When it completes successfully you will see:

```
==> Done! 'clean-grocery-bot' deployed successfully.
```

**Set the AI model environment variable:**

After the first deploy, tell Lambda which Bedrock model to use:

```bash
aws lambda update-function-configuration \
    --function-name clean-grocery-bot \
    --region us-east-2 \
    --environment "Variables={BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0}"
```

!!! tip "Switching models later"
To switch to a different model at any time — no redeploy needed:
`bash
    aws lambda update-function-configuration \
        --function-name clean-grocery-bot \
        --region us-east-2 \
        --environment "Variables={BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0}"
    `
Remember to also add the new model's ARNs to the IAM policy (see Troubleshooting → Switching AI models).

**Set the Lambda handler:**

After the deploy completes, you need to tell Lambda which function in your code to call:

1. Go to the Lambda console and open the `clean-grocery-bot` function.
2. Click the **Code** tab.
3. Scroll down to **Runtime settings** and click **Edit**.
4. Set **Handler** to: `clean_grocery_bot.lambda_handler.handler`
5. Click **Save**.

---

## Step 14: Register the Telegram Webhook

This tells Telegram where to send messages — your API Gateway URL.

Run this command in your terminal, replacing the three placeholder values:

```bash
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
    -H "Content-Type: application/json" \
    -d '{
        "url": "https://YOUR_API_GATEWAY_INVOKE_URL/webhook",
        "secret_token": "YOUR_WEBHOOK_SECRET"
    }'
```

Replace:

- `YOUR_BOT_TOKEN` — the token from Step 1.2
- `YOUR_API_GATEWAY_INVOKE_URL` — the invoke URL from Step 9 (without trailing slash)
- `YOUR_WEBHOOK_SECRET` — the string from Step 10

**Expected response:**

```json
{ "ok": true, "result": true, "description": "Webhook was set" }
```

If you see `"ok":true`, the webhook is registered. Telegram will now deliver every message to your bot directly to your Lambda function.

!!! tip "Windows users"
`curl` is available in Windows 10 and 11 in both Command Prompt and PowerShell. If you have trouble with the single quotes in the `-d` argument, try Git Bash instead, where the command works as written above.

---

## Step 15: Test Your Bot

1. Open Telegram and find your bot by searching for its username.
2. Send `/start` to begin the conversation.
3. Try these test messages:

| Message to send  | What you should receive         |
| ---------------- | ------------------------------- |
| `yogurt`         | 3 clean yogurt recommendations  |
| `top 5 crackers` | Up to 5 cracker recommendations |
| `3 cereals`      | Up to 3 cereal recommendations  |

A typical response looks like:

```
Results for "yogurt":

1. Stonyfield Organic Plain Whole Milk Yogurt (Stonyfield)
✅ Very Clean — Score: 92/100
• Certified organic with only 3 ingredients
• No artificial additives or preservatives
• Whole milk base — no seed oils

2. ...
```

!!! note "First query may be slower"
Your first query may take 5–10 seconds while Lambda initializes ("cold start"). Subsequent queries within a few minutes will respond faster.

---

## Troubleshooting

### The bot does not respond at all

Check each of the following in order:

1. **Webhook registered correctly?** Re-run the `curl` command from Step 14 and confirm you see `"ok":true`.
2. **Correct API Gateway URL?** The URL in your `setWebhook` call must end with `/webhook` and must exactly match the invoke URL from Step 9.
3. **Check CloudWatch logs:** In the AWS Console, open **CloudWatch** → **Log groups** and look for `/aws/lambda/clean-grocery-bot`. If there is no log group, the Lambda function has never been triggered — the issue is in webhook registration or API Gateway configuration.
4. **Lambda handler set correctly?** In the Lambda console → Code tab → Runtime settings, confirm the handler is `clean_grocery_bot.lambda_handler.handler`.
5. **Is your chat ID in the allowed list?** The bot silently ignores messages from non-whitelisted chat IDs. Check the `allowed-chat-ids` parameter in Parameter Store.

### The bot responds with "Sorry, something went wrong"

This means Lambda ran but hit an error. Check CloudWatch logs:

1. Open **CloudWatch** → **Log groups** → `/aws/lambda/clean-grocery-bot`.
2. Click the most recent log stream.
3. Look for `ERROR` lines.

Common causes:

- **Missing `BEDROCK_MODEL_ID` environment variable** — confirm the variable is set (Step 13). Check with:

  ```bash
  aws lambda get-function-configuration \
      --function-name clean-grocery-bot \
      --region us-east-2 \
      --query 'Environment'
  ```

- **Missing Parameter Store values** — verify all three parameters exist:

  ```bash
  aws ssm get-parameter --name "/clean-grocery-bot/telegram-token" --with-decryption
  aws ssm get-parameter --name "/clean-grocery-bot/webhook-secret" --with-decryption
  aws ssm get-parameter --name "/clean-grocery-bot/allowed-chat-ids" --with-decryption
  ```

- **Lambda timeout** — confirm the timeout is set to 30 seconds (Step 8).

### I get a 403 Forbidden error in CloudWatch logs

The webhook secret does not match. This happens if the `secret_token` in the `setWebhook` call does not match the value stored in `/clean-grocery-bot/webhook-secret` in Parameter Store.

Fix: re-store the parameter with the correct value using `--overwrite`, then re-register the webhook:

```bash
aws ssm put-parameter \
    --name "/clean-grocery-bot/webhook-secret" \
    --value "YOUR_CORRECT_WEBHOOK_SECRET" \
    --type SecureString \
    --overwrite
```

Then re-run the `setWebhook` curl command from Step 14.

### `No module named 'pydantic_core._pydantic_core'`

This means the Lambda package was built for a **different CPU architecture** than the Lambda runtime. The compiled `.so` extension for the build machine's architecture cannot be loaded on a different one.

The `deploy.sh` script automatically detects the build machine architecture and sets the Lambda architecture to match. If this error appears:

1. Confirm `deploy.sh` ran without errors and the output included a line like:

   ```text
   ==> Build machine: aarch64 → Lambda architecture: arm64
   ```

2. Check what architecture is actually set on the Lambda:

   ```bash
   aws lambda get-function-configuration \
       --function-name clean-grocery-bot \
       --region us-east-2 \
       --query 'Architectures'
   ```

3. If the architecture does not match your machine, re-run `bash deploy.sh` — it will correct it automatically.

### `Invocation of model ID … with on-demand throughput isn't supported`

Newer Bedrock models require an **inference profile** ID, not the bare model ID. The profile ID is the model ID prefixed with `us.`:

| Wrong (bare model ID)                      | Correct (inference profile)                   |
| ------------------------------------------ | --------------------------------------------- |
| `amazon.nova-2-lite-v1:0`                  | `us.amazon.nova-2-lite-v1:0`                  |
| `anthropic.claude-haiku-4-5-20251001-v1:0` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

Fix: update the `BEDROCK_MODEL_ID` environment variable to use the `us.` prefix:

```bash
aws lambda update-function-configuration \
    --function-name clean-grocery-bot \
    --region us-east-2 \
    --environment "Variables={BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0}"
```

### `AccessDeniedException: not authorized to perform bedrock:InvokeModel`

The IAM role's inline policy does not include the model or inference profile you are trying to use. Every model needs **two ARNs** in the policy: the foundation model and the inference profile.

Update the policy to add them:

```bash
aws iam put-role-policy \
    --role-name clean-grocery-bot-role \
    --policy-name clean-grocery-bot-inline-policy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "bedrock:InvokeModel",
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0",
                    "arn:aws:bedrock:*:*:inference-profile/us.amazon.nova-2-lite-v1:0"
                ]
            },
            {
                "Effect": "Allow",
                "Action": "ssm:GetParameter",
                "Resource": "arn:aws:ssm:*:*:parameter/clean-grocery-bot/*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "*"
            }
        ]
    }'
```

### `ResourceNotFoundException: Model use case details have not been submitted`

This only applies to **Anthropic models** (Claude). AWS requires a one-time use case form before an account can invoke any Claude model.

1. Open the [Bedrock Model Catalog](https://us-east-2.console.aws.amazon.com/bedrock/home?region=us-east-2#/models) in us-east-2.
2. Find the Claude model and look for the **"Submit use case details"** button.
3. Complete and submit the form.
4. Wait 15 minutes, then retry.

To avoid this entirely, use Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`) — it has no use case form requirement.

### Switching AI models

The active model is controlled by the `BEDROCK_MODEL_ID` Lambda environment variable. No code change or redeploy is needed to switch:

```bash
# Switch to Claude Haiku 4.5 (requires Anthropic use case form — see above)
aws lambda update-function-configuration \
    --function-name clean-grocery-bot \
    --region us-east-2 \
    --environment "Variables={BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0}"

# Switch back to Amazon Nova 2 Lite
aws lambda update-function-configuration \
    --function-name clean-grocery-bot \
    --region us-east-2 \
    --environment "Variables={BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0}"
```

After switching, also update the IAM policy to include the new model's ARNs (see `AccessDeniedException` section above).

### The deploy.sh script fails

Common causes:

- **`uv` not installed** — run `uv --version`. If missing, follow Step 3.3.
- **`uv` version too old** — run `uv self update` to get the latest version.
- **AWS CLI not configured** — run `aws sts get-caller-identity`. If this fails, redo Step 4.2.
- **Wrong AWS region** — the deploy script defaults to `us-east-2`. If your Lambda is in a different region, set `export AWS_REGION=your-region` before running.
- **Lambda function does not exist** — confirm a function named `clean-grocery-bot` exists in the Lambda console in the correct region.

### I want to add another family member

1. Ask them to find their chat ID using @userinfobot (Step 2).
2. Update the `allowed-chat-ids` parameter with both IDs:

   ```bash
   aws ssm put-parameter \
       --name "/clean-grocery-bot/allowed-chat-ids" \
       --value "YOUR_CHAT_ID,THEIR_CHAT_ID" \
       --type SecureString \
       --overwrite
   ```

   No redeployment is needed. The Lambda function reads this value fresh on each startup.

### I want to change my dietary preferences after deployment

1. Edit `dietary_preference_config.json` in the repository folder.
2. Re-run the deploy script:

   ```bash
   export LAMBDA_FUNCTION_NAME=clean-grocery-bot
   export AWS_REGION=us-east-2
   bash deploy.sh
   ```

   No other changes are needed — the config file is bundled into the Lambda package on each deploy.
