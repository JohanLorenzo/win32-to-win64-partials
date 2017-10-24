import requests
import taskcluster
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from taskcluster.utils import stableSlugId, encryptEnvVar, slugId
from chunkify import chunkify
import arrow
import yaml
from jose import jws
from jose.constants import ALGORITHMS
from functools import partial
import time

# TODO: use a config file to pass branch, from, to, platforms
BRANCH = "mozilla-release"
REPO_PATH = "releases/{}".format(BRANCH)
FROM = {
    "version": "56.0",
    "build_number": 6
}
TO = {
    "version": "56.0.2",
    "build_number": 1
}
PLATFORMS = ("win32",)   # for bouncers

bouncer_platform_map = {
    'win32': 'win',
    'win64': 'win64',
    'linux': 'linux',
    'linux64': 'linux64',
    'macosx64': 'osx'
}


def find_task_id_from_route(route):
    index = taskcluster.Index()
    return index.findTask(route)["taskId"]


def buildbot2bouncer(platform):
    return bouncer_platform_map.get(platform, platform)


def get_locales(repo_path, version, revision=None):
    tag = "FIREFOX_{}_RELEASE".format(version.replace(".", "_"))
    url = "https://hg.mozilla.org/{}/raw-file/{}/" \
        "browser/locales/shipped-locales".format(repo_path, revision or tag)
    req = requests.get(url)
    req.raise_for_status()
    # FIXME: mac is different!
    locales = [
        line.split()[0] for line in req.text.splitlines()
        if not line.startswith("ja-JP-mac")
    ]
    return locales


def sign_task(task_id, pvt_key, valid_for=3600, algorithm=ALGORITHMS.RS512):
    # reserved JWT claims, to be verified
    # Issued At
    iat = int(time.time())
    # Expiration Time
    exp = iat + valid_for
    claims = {
        "iat": iat,
        "exp": exp,
        "taskId": task_id,
        "version": "1",
    }
    return jws.sign(claims, pvt_key, algorithm=algorithm)


from_locales = get_locales(repo_path=REPO_PATH, version=FROM["version"])
to_locales = get_locales(repo_path=REPO_PATH, version=TO["version"],
                         revision="3e4ce49f3214e87a52a2b70ca7fbdffe20bef362")
common_locales = set(from_locales) & set(to_locales)

with open("id_rsa") as f:
    pvt_key = f.read()

with open("config.yml") as f:
    cfg = yaml.safe_load(f)


tc_config = {
    "credentials": {
        "clientId": cfg["taskcluster_client_id"],
        "accessToken": cfg["taskcluster_access_token"]
    }
}

now = arrow.now()
now_ms = now.timestamp * 1000

env = Environment(loader=FileSystemLoader(["."]), undefined=StrictUndefined,
                  extensions=['jinja2.ext.do'])
template = env.get_template("graph.yml.tmpl")
template_vars = {
    "branch": BRANCH,
    "platforms": PLATFORMS,
    "locales": common_locales,
    "chunks": 10,
    "from_version": FROM["version"],
    "from_build_number": FROM["build_number"],
    "to_version": TO["version"],
    "to_build_number": TO["build_number"],
    "stableSlugId": stableSlugId(),
    "chunkify": chunkify,
    "sorted": sorted,
    "now": now,
    "now_ms": now_ms,
    "never": arrow.now().replace(years=1),
    "encrypt_env_var": lambda *args: encryptEnvVar(
        *args, keyFile='docker-worker-pub.pem'),
    "sign_task": partial(sign_task, pvt_key=pvt_key),

    "balrog_username": cfg["balrog_username"],
    "balrog_password": cfg["balrog_password"],
    "beetmover_candidates_bucket": "net-mozaws-prod-delivery-firefox",
    "beetmover_aws_access_key_id": cfg["beetmover_aws_access_key_id"],
    "beetmover_aws_secret_access_key": cfg["beetmover_aws_secret_access_key"],
    "product": "firefox",
    "repo_path": "releases/mozilla-release",
    "mozharness_changeset": "default",
    "signing_class": "release-signing",
    "build_tools_repo_path": "build/tools",
    "buildbot2bouncer": buildbot2bouncer,
    "funsize_update_generator_image_task": find_task_id_from_route("releases.v1.mozilla-release.latest.firefox.latest.funsize_update_generator_image"),
    "funsize_balrog_submitter_image_task": find_task_id_from_route("releases.v1.mozilla-release.latest.firefox.latest.funsize_balrog_image"),
    "beetmover_image_task": find_task_id_from_route("releases.v1.mozilla-release.latest.firefox.latest.beetmove_image"),
    "for_sure": True,
}

graph_repr = template.render(**template_vars)
graph = yaml.safe_load(graph_repr)
# Print graph for external use, like in https://github.com/rail/graph2tasks
#print(yaml.safe_dump(graph))

scheduler = taskcluster.Scheduler(tc_config)
graph_id = slugId()
#print(scheduler.createTaskGraph(graph_id, graph))
