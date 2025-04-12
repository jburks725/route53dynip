# Route 53 Dynamic IP

A simple Python script running in a Docker container to maintain an A record
in Route 53 for a dynamic IP. Why pay (more) for DDNS services?

## What It Does

When it starts, this Python script takes the FQDN you've passed in and
attempts to find the ZoneId of the Route 53 hosted zone to add the entry
to. It does this by iteratively stripping the left-most label from the FQDN
(starting with the FQDN, in case you want your A record at a zone apex) until
it finds a hosted zone whose name matches. If it cannot find one, it prints
out an error message and exits.

After getting the ZoneId, the script executes the following in an infinite
loop:
1. It makes a call to http://ipinfo.io/json to get your current
IP address. If it cannot retrieve the IP (rate limiting?), skip to step 4.
1. It looks up the FQDN in the hosted zone and compares the current IP address
to the one looked up in step 1. If they match, skip to step 4.
1. It executes `Route53.ChangeResourceRecordSets` to UPSERT an A record with
a 5 minute TTL pointing to the current IP address.
1. Sleep for 30 minutes or exit if `--onetime` is passed as an argument.

## How to Run

```text
$ python3 route53dynip.py --help
usage: route53dynip.py [-h] [--onetime] fqdn

positional arguments:
  fqdn        the FQDN to point your IP to

optional arguments:
  -h, --help  show this help message and exit
  --onetime   update the DNS entry and exit
```

### Rate Limits at http://ipinfo.io

This service currently rate-limits you to 1000 requests a day. I chose to poll
on a 30 minute interval. If your IP address is changing more often than that,
you either need to change ISPs, consider paying them for a static IP, or host
whatever you're hosting at AWS directly and leverage other AWS features like
Route 53 Alias Records and ALBs/ELBs.

### Providing Credentials

You need to provide AWS credentials to the Python script in order to run this.
You can do this in one of two ways: environment variables, or mounting an
AWS `credentials` file as a volume. If you create a separate profile in your
credentials file, you can specify the `AWS_PROFILE` environment variable to
use it.

```bash
# Pass credentials directly via environment variables
$ docker run -d -e AWS_ACCESS_KEY_ID={YOUR_KEY} -e AWS_SECRET_ACCESS_KEY=\
{YOUR_SECRET_KEY} jburks725/route53dynip mydynamic.hostname.com
# OR use a credentials file with a profile (named route53 in the example)
# and mount your credentials into the container
$ docker run -d -e AWS_PROFILE=route53 -v $HOME/.aws:/.aws \
jburks725/route53dynip mydynamic.hostname.com
```

### IAM Policy

It's recommended that you create a separate IAM user for running this, and
that you grant it only the permissions necessary to create the A record
you want.

You'll want to look up the Route 53 ZoneId of the target Hosted Zone, 
and substitute it into the policy below. This allows listing your zones, 
and modifications to only the appropriate zone.

Use the following AWS CLI command, or the AWS Console, to look up your
ZoneId. 

```terminal
aws route53 list-hosted-zones-by-name --dns-name {yourdomain}.com. --max-items 1 --output json | jq -r '.HostedZones[0].Id' | cut -d/ -f3
```

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "route53:ListHostedZones",
                "route53:ListHostedZonesByName"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "route53:ListResourceRecordSets",
                "route53:ChangeResourceRecordSets"
            ],
            "Resource": [
                "arn:aws:route53:::hostedzone/#{ZoneIdHere}"
            ]
        }
    ]
}
```

Once you've created that policy, create a new IAM user and generate a keypair
for it. You may create a profile in your `~/.aws/credentials` file, or pass
the credentials directly via environment variables.

## Building the Docker image(s)

The `Dockerfile`s in this repo will be an image based on Chainguard's latest `python`
image, using their dev image to install the Boto3 library. The Makefile has targets to
build the image locally as well as use `buildx` to build multi-arch images. 

The default architectures are `amd64`, `arm32v7`, and `arm64`, which can be overridden
with the `ARCHES` variable when running make.

There are also Make targets for pushing to Dockerhub, execute unit tests, and clean up
the images in your local Docker daemon.

It copies the Python script into `/route53dynip`, and executes as user `nonroot`.

The latest version of this image should be available on DockerHub at
https://hub.docker.com/r/jburks725/route53dynip/.

## Running the container in Docker

The Python script is the `ENTRYPOINT`, so you need only specify the
FQDN you want added to Route 53 Hosted Zone as an argument to the `docker run`
command.

## Running the deployment in Kubernetes

Assuming your K8s cluster is running on a supported architecture, you should
be able to run this using the included YAML files. You'll need to make some
changes to these files to deploy.

### Secrets

Edit the `secrets.yaml` file to add your AWS Access and Secret keys in the appropriate
places (look for the `{{}}` markers). Then deploy this to your cluster using `kubectl create -f secrets.yaml`.

### Deployment as a Service

Edit `deployment.yaml` to put the FQDN you want the utility to maintain in the `args` portion of the 
pod template spec. Deploy it using `kubectl create -f deployment.yaml`. *Make sure you've created the
secrets first!*

### Deployment as a Cron Job

Edit `cronjob.yaml` to put the FQDN you want the utility to maintain in the `args` portion of the 
pod template spec. By default, the job will run every half hour. You can edit the schedule on line 6 if
you'd like. See [crontab guru](https://crontab.guru) for more information on cron job schedule syntax.

# TODO
- [x] Add a license statement
- [x] Add multiarch support
- [x] Add basic Kubernetes support
- [x] Add support as a Kubernetes cronjob
- [x] Convert to proper Docker multi-arch build
- [x] Add unit tests
- [ ] Helm Chart
- [ ] Allow customization of TTL
- [ ] Allow custom polling interval (currently 30 minutes)
- [ ] Maybe some logging verbosity control?
- [ ] Learn Python better!

## Running Tests

The project includes a comprehensive test suite to verify functionality. There are several ways to run the tests:

### Local Testing

```bash
# Run the basic test suite
make test

# Run tests with code coverage reporting
make test-coverage
```

### Docker-based Testing

```bash
# Build and run tests in Docker container
make test-docker
```

This ensures the application works as expected in isolation, which is especially useful for CI/CD pipelines.
