FROM python:3.13
WORKDIR /usr/local/app

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git

# Install the application dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy in the source code
COPY . .
EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# # Setup an app user so the container doesn't run as the root user
# RUN useradd app
# USER app

# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
# ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
# CMD [ "streamlit", "hello",  "--server.port=8501", "--server.address=0.0.0.0"]
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0" ]