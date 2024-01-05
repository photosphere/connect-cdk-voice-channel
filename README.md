## About Amazon Connect Voice Channel Deployment CDK
This solution can be used to create agents/queues/flows/hoursofoperation in Amazon Connect.

### Requirements

1.[AWS CDK 2.100.0 installed](https://docs.aws.amazon.com/cdk/v2/guide/home.html)

2.[NodeJS 14.x installed](https://nodejs.org/en/download/)

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
### Or Build and run the Application on Cloud9

```bash
streamlit run connect_cdk_voice_channel/connect_cdk_voice_channel_stack.py --server.port 8080 --server.address=0.0.0.0 
