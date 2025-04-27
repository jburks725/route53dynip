FROM cgr.dev/chainguard/python:latest-dev AS builder

WORKDIR /route53dynip
RUN python -m venv venv
ENV PATH=/route53dynip/venv/bin:$PATH
COPY requirements.txt requirements.txt
# Install libraries
RUN pip install -r requirements.txt

FROM cgr.dev/chainguard/python:latest
# Run as non-root user (Chainguard images typically already use a non-root user)
USER nonroot

WORKDIR /route53dynip

# Set Python to run unbuffered for proper log streaming
ENV PYTHONUNBUFFERED=TRUE
ENV PATH=/route53dynip/venv/bin:$PATH

# Copy the application script
COPY route53dynip.py route53dynip.py
COPY --from=builder /route53dynip/venv /route53dynip/venv


# Set the entrypoint
ENTRYPOINT ["python", "route53dynip.py"]
