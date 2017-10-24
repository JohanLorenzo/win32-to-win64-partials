import requests
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from taskcluster import Scheduler
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
    "version": "56.0.1",
    "build_number": 2
}
PLATFORMS = ("win32",)   # for bouncers


bouncer_platform_map = {
    'win32': 'win',
    'win64': 'win64',
    'linux': 'linux',
    'linux64': 'linux64',
    'macosx64': 'osx'
}

complete_to_mar_task_ids_per_chunk_map = {
    1: 'eM2m3jIfSLuJyvJFZ186SQ',
    10: 'GK7vdU3KS9eQ4ybKKfGctw',
    2: 'fYOP2ttPQNWeE6ARKrr5hQ',
    3: 'O6Upgz_ZQ_q4Uvniy8iNLQ',
    4: 'NYDp2D-MTyCgFrooZ7q5gQ',
    5: 'NDJ3rsH7TIqRmCqm4ZcJGw',
    6: 'KcW6rfarTJi47hUVqsmdiQ',
    7: 'MS4S0i_LTFqaxM2T8rx1hw',
    8: 'd_VhAiurTOer70d_loPBGA',
    9: 'Gub9Dj_CRd2RqDy0GCjlag',
}
en_us_mar_task_id = 'fRPlsYotQZCSMfICJJJ6wA'

def buildbot2bouncer(platform):
    return bouncer_platform_map.get(platform, platform)


def complete_to_mar_task_ids_per_chunk(chunk):
    return complete_to_mar_task_ids_per_chunk_map[chunk]


def get_locales(repo_path, version, revision=None):
    tag = "FIREFOX_{}_RELEASE".format(version.replace(".", "_"))
    url = "https://hg.mozilla.org/{}/raw-file/{}/" \
        "browser/locales/shipped-locales".format(repo_path, revision or tag)
    req = requests.get(url)
    req.raise_for_status()
    # FIXME: mac is different!
    locales = [
        line.split()[0] for line in req.text.splitlines()
        if not (line.startswith("ja-JP-mac") or line.startswith("en-US"))
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
    "complete_to_mar_task_ids_per_chunk": complete_to_mar_task_ids_per_chunk,
    "complete_en_us_mar_task_id": en_us_mar_task_id,
    "for_sure": True,
}

graph_repr = template.render(**template_vars)
graph = yaml.safe_load(graph_repr)
print(yaml.safe_dump(graph))

scheduler = Scheduler(tc_config)
graph_id = slugId()
#print(scheduler.createTaskGraph(graph_id, graph))
