# OpenBeavs

OpenBeavs for CS Capstone. Team # 043

A model for collaboration between Oregon State AI agents, utilizing context to provide users with better responses to queries.

Team Roster/Contacts:

James Smith
#: 5037138776
email: smitjam2@oregonstate.edu , galavantinggeckoguy@gmail.com
GH: gitJamoo

Minsu Kim
#: 971-297-4257
Email: kimminsu@oregonstate.edu , minsteww26@gmail.com
GH: minkim26

Rohan Thapliyal
#: 5035236168
email: thapliyr@oregonstate.edu , rohanthapliyal2020@gmail.com
GH: Rohanthap

Long Tran
#: 541 207 5609
email: tranlon@oregonstate.edu
GH: longtran921

John Sweet
#: 2135456760
email: john.sweet@oregonstate.edu
GH: jsweet8258

#eof#

## Project Structure

- `front/`: OpenBeavs - An AI Agent Registry platform with A2A protocol support.
- `back/`: Contains the FastAPI backend application.
- `deploy.sh`: A script to deploy both applications to Google Cloud Run.

## OpenBeavs & Agent Registry

This project is the **OpenBeavs** platform that features a decentralized **A2A Agent Registry**.
- **Agent Registry**: Discover, share, and install AI agents.
- **Workspace Integration**: Manage agents directly from the UI.
- **A2A Protocol**: Full support for Agent-to-Agent communication.

For detailed documentation, please refer to [front/README.md](./front/README.md).

## Prerequisites

- [Docker](https://www.docker.com/)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- [Node.js and npm](https://nodejs.org/)

## Local Development

### Backend

1.  Navigate to the `back` directory:
    ```bash
    cd back
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the development server:
    ```bash
    uvicorn main:app --reload
    ```
    The backend will be available at `http://localhost:8000`.

- Note: To lint, use `ruff check`

### Frontend (OpenBeavs)

For detailed setup and development instructions for the OpenBeavs frontend, please refer to [front/README.md](./front/README.md).

## Deployment

1.  **Authenticate with GCP:**

    ```bash
    gcloud auth login
    gcloud auth configure-docker
    ```

2.  **Configure the `deploy.sh` script:**

    Open `deploy.sh` and replace the following placeholder values with your GCP project ID and desired region:

    - `your-gcp-project-id`
    - `your-gcp-region`

3.  **Run the deployment script:**

    ```bash
    ./deploy.sh
    ```

    The script will build and deploy both the backend and frontend applications to Google Cloud Run. The frontend will be automatically configured to communicate with the deployed backend.
