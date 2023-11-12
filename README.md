## About Amazon Connect Voice Channel Deployment CDK
This solution can be used to create agents/queues/flows/hoursofoperation in Amazon Connect.

### Installation

Clone the repo

```bash
git clone https://github.com/photosphere/connect-cdk-voice-channel.git
```

cd into the project root folder

```bash
cd connect-cdk-voice-channel
```

#### Create virtual environment

##### via python

Then you should create a virtual environment named .venv

```bash
python -m venv .venv
```

and activate the environment.

On Linux, or OsX 

```bash
source .venv/bin/activate
```
On Windows

```bash
source.bat
```

Then you should install the local requirements

```bash
pip install -r requirements.txt
```
### Build and run the Application Locally

```bash
streamlit run connect_cdk_voice_channel/connect_cdk_voice_channel_stack.py
```

