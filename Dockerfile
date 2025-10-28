# Note: 
# Within docker, this container runs as root as no user is specified.
# Due to the nature of the lambda function, this is acceptable as Lambda defines the default user
# to have the least-privilege permissions rather than the root user.

# Therefore we can ignore the linting error for this Dockerfile
# as it is not a security risk for this specific use case.

# Ignored in .trivyignore also.
#kics-scan disable=fd54f200-402c-4333-a5a4-36ef6709af2f
#checkov:skip=CKV_DOCKER_3:Lambda makes default user lowest privilege

FROM public.ecr.aws/lambda/python:3.12

# Install git using dnf (https://docs.aws.amazon.com/lambda/latest/dg/python-image.html#python-image-base)
# For python 3.12, dnf replaces yum for package management
RUN dnf install -y git-2.40.1 && dnf clean all

# Copy the poetry.lock and pyproject.toml files
COPY pyproject.toml poetry.lock ${LAMBDA_TASK_ROOT}/

# Install the dependencies
WORKDIR ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir poetry==1.5.0 &&\
    poetry config virtualenvs.create false &&\ 
    poetry install --only main

# Copy the source code into the container
COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY config/ ${LAMBDA_TASK_ROOT}/config/

HEALTHCHECK NONE

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "src.main.handler" ]