# Copyright by AcmaTvirus
# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Remove windows-curses from requirements.txt as it's not needed on Linux
# And add curses-menu if needed, but we'll use log_mode for Docker
RUN sed -i '/windows-curses/d' requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Set environment variables
ENV DOCKER_CONTAINER=true
ENV PYTHONUNBUFFERED=1

# Define the command to run the application
# We use -u for unbuffered output to see logs in real-time
ENTRYPOINT ["python", "-u", "main.py"]
