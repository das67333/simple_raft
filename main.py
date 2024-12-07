import enum
import dataclasses
import flask
import functools
import sys
import random
import requests
import threading

from storage import *


app = flask.Flask(__name__)
storage = Storage()

idx, ports = int(sys.argv[1]), list(map(int, sys.argv[2:]))
hosts = list(map(lambda port: f'http://127.0.0.1:{port}/', ports))
other_hosts = set(hosts) - {f'http://127.0.0.1:{ports[idx]}/'}
storage = Storage()
leader_host, own_host = hosts[0], hosts[idx]

disabled = False


################################################################
# utils


def eprint(x):
    print(f'\033[92m{x}\033[0m', file=sys.stderr)


def redirect_to_leader():
    eprint('Redirecting to leader')
    return flask.redirect(f'{leader_host}/data')


def replicate_modification(modification):
    data = {
        'term': hc.term,
        'modifications': [modification.asdict()],
        'src': own_host,
    }
    for host in other_hosts:
        try:
            requests.post(f'{host}/append_entries',
                          json=data, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            pass


def request_modifications_on_detected_gap_in_log(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DetectedGapInLog as e:
            data = {'sn_from': e.sn_from}
            try:
                response = requests.post(
                    f'{leader_host}/request_modifications', json=data, timeout=REQUEST_TIMEOUT)
                modifications = response.json()['modifications']
                for modification in map(StorageModification.fromdict, modifications):
                    storage.add_modification(modification)
            except requests.exceptions.RequestException:
                pass
            return wrapper(*args, **kwargs)
    return wrapper

################################################################
# Internal handlers


k = 1
LEADER_TIMEOUT_MIN = 3.0 * k
LEADER_TIMEOUT_MAX = 5.0 * k
REQUEST_TIMEOUT = 0.1
VOTING_TIMEOUT = 2.0 * k
HEARTBEAT_INTERVAL = 1.0 * k


class Role(enum.Enum):
    LEADER = 1
    FOLLOWER = 2
    CANDIDATE = 3


def eprint(x):
    print(f'\033[92m{x}\033[0m', file=sys.stderr)

################################################################
# health check: timers, roles, elections


@dataclasses.dataclass
class HealthCheck:
    mutex = threading.Lock()
    role: Role = None
    checking_leader = None  # if follower
    sending_heartbeat = None  # if leader
    term = 0
    votes_history = {}

    def __post_init__(self):
        if own_host == leader_host:
            self.become_leader(immediate_heartbeats=False)
        else:
            self.become_follower()

    def become_leader(self, immediate_heartbeats=True):
        if self.role != Role.LEADER:
            eprint(f'I\'ve become leader for term={self.term}')
        self.role = Role.LEADER
        global leader_host
        leader_host = own_host
        self.stop_checking_leader()
        self.stop_sending_heartbeats()
        self.start_sending_heartbeats(immediate=immediate_heartbeats)

    def become_follower(self):
        if self.role != Role.FOLLOWER:
            eprint(f'I\'ve become follower for term={self.term}')
        self.role = Role.FOLLOWER
        self.stop_sending_heartbeats()
        self.restart_checking_leader()

    def run_elections(self, term: int):
        if self.role == Role.LEADER or self.term != term or disabled:
            return
        if self.role != Role.CANDIDATE:
            eprint(f'I START ELECTIONS for term={term}')
        else:
            eprint(f'REPEATING ELECTIONS for term={term}')
        self.role = Role.CANDIDATE

        voting = threading.Timer(
            interval=VOTING_TIMEOUT, function=HealthCheck.run_elections, args=(self, term))
        voting.start()
        votes = 1  # own vote
        hc.votes_history[term] = own_host
        data = {
            'term': term,
            'log_size': len(storage.log),
            'src': own_host,
        }
        for host in other_hosts:
            try:
                response = requests.post(f'{host}/request_vote', json=data,
                                         timeout=REQUEST_TIMEOUT)
                vote_granted = response.json()['vote_granted']
                if vote_granted:
                    eprint(f'GRANTED VOTE FROM {host} for term={term}')
                    votes += 1
            except requests.exceptions.RequestException:
                pass
        if votes >= (len(other_hosts) + 3) // 2:  # strict majority (>=n/2 + 1)
            self.term += 1
            voting.cancel()
            self.become_leader()

    def start_sending_heartbeats(self, immediate=True):
        if self.role != Role.LEADER:
            return

        self.sending_heartbeat = threading.Timer(
            interval=HEARTBEAT_INTERVAL, function=HealthCheck.start_sending_heartbeats, args=(self,))
        self.sending_heartbeat.start()
        if not immediate:
            return

        data = {
            'term': self.term,
            'modifications': [],
            'src': own_host,
        }
        for host in other_hosts:
            try:
                requests.post(f'{host}/append_entries',
                              json=data, timeout=REQUEST_TIMEOUT)
            except requests.exceptions.RequestException:
                pass

    def restart_checking_leader(self):
        if self.role != Role.FOLLOWER:
            return
        if self.checking_leader is not None:
            self.checking_leader.cancel()
        timeout = random.uniform(LEADER_TIMEOUT_MIN, LEADER_TIMEOUT_MAX)
        self.checking_leader = threading.Timer(
            interval=timeout, function=HealthCheck.run_elections, args=(self, self.term))
        self.checking_leader.start()

    def stop_sending_heartbeats(self):
        if self.sending_heartbeat is not None:
            self.sending_heartbeat.cancel()
            self.sending_heartbeat = None

    def stop_checking_leader(self):
        if self.checking_leader is not None:
            self.checking_leader.cancel()
            self.checking_leader = None


hc = HealthCheck()

################################################################
# Internal handlers


@app.route('/request_vote', methods=['POST'])
def request_vote():
    if disabled:
        return 'Server is disabled\n', 403
    term, log_size = flask.request.json['term'], flask.request.json['log_size']
    with hc.mutex:
        if term < hc.term:
            return 'Old term\n', 403
        if term > hc.term:
            global leader_host
            leader_host = flask.request.json['src']
            hc.term = term
            hc.become_follower()
        if term not in hc.votes_history and log_size >= len(storage.log):
            hc.votes_history[term] = flask.request.host
        vote_granted = hc.votes_history.get(term) == flask.request.host
    return flask.jsonify({'vote_granted': vote_granted}), 200


@app.route('/append_entries', methods=['POST'])
@request_modifications_on_detected_gap_in_log
def append_entries():
    if disabled:
        return 'Server is disabled\n', 403
    term = flask.request.json['term']
    with hc.mutex:
        if term < hc.term:
            return 'Old term\n', 403
        if term > hc.term:
            global leader_host
            leader_host = flask.request.json['src']
            hc.term = term
            hc.become_follower()
        hc.restart_checking_leader()
    for modification in map(StorageModification.fromdict, flask.request.json['modifications']):
        storage.add_modification(modification)
    return '', 200


@app.route('/request_modifications', methods=['POST'])
def request_modifications():
    if own_host != leader_host:
        return redirect_to_leader()
    sn_from = flask.request.json['sn_from']
    data = list(map(lambda x: x.asdict(), storage.log[sn_from:]))
    return flask.jsonify({'modifications': data}), 200


################################################################
# Extrernal handlers


@app.route('/data', methods=['POST'])
@request_modifications_on_detected_gap_in_log
def create():
    if disabled:
        return 'Server is disabled\n', 403
    if own_host != leader_host:
        return redirect_to_leader()
    sn = storage.generate_sn()
    modification = StorageModification(
        sn=sn,
        id=sn,
        type=StorageModificationType.CREATE,
        value=flask.request.json['value']
    )
    try:
        storage.add_modification(modification)
    except DetectedGapInLog as e:
        # TODO
        raise NotImplementedError()
    except DroppedModification:
        return flask.jsonify({'error': 'Ineligible modification'}), 409
    replicate_modification(modification)
    return flask.jsonify({'id': modification.id}), 201


@app.route('/data/<int:id>', methods=['GET'])
def read(id: int):
    if disabled:
        return 'Server is disabled\n', 403
    if (value := storage.get_value(id)) is None:
        return flask.jsonify({'status': 'Not found'}), 404
    else:
        return flask.jsonify({'value': value}), 200


@app.route('/data/<int:id>', methods=['PUT'])
@request_modifications_on_detected_gap_in_log
def update(id: int):
    if disabled:
        return 'Server is disabled\n', 403
    if own_host != leader_host:
        return redirect_to_leader()
    modification = StorageModification(
        sn=storage.generate_sn(),
        id=id,
        type=StorageModificationType.UPDATE,
        value=flask.request.json['value']
    )
    try:
        storage.add_modification(modification)
    except DroppedModification:
        return flask.jsonify({'error': 'Ineligible modification'}), 409
    replicate_modification(modification)
    return '', 200


@app.route('/data/<int:id>', methods=['DELETE'])
@request_modifications_on_detected_gap_in_log
def delete(id: int):
    if disabled:
        return 'Server is disabled\n', 403
    if own_host != leader_host:
        return redirect_to_leader()
    modification = StorageModification(
        sn=storage.generate_sn(),
        id=id,
        type=StorageModificationType.DELETE
    )
    try:
        storage.add_modification(modification)
    except DroppedModification:
        return flask.jsonify({'status': 'Not found'}), 404
    replicate_modification(modification)
    return '', 200


@app.route('/data/<int:id>/cas', methods=['PUT'])
@request_modifications_on_detected_gap_in_log
def cas(id: int):
    if disabled:
        return 'Server is disabled\n', 403
    if own_host != leader_host:
        return redirect_to_leader()
    modification = StorageModification(
        sn=storage.generate_sn(),
        id=id,
        type=StorageModificationType.CAS,
        value=flask.request.json['value'],
        old_value=flask.request.json['old_value']
    )
    try:
        storage.add_modification(modification)
    except DroppedModification:
        return flask.jsonify({'status': 'CAS failed'}), 412
    replicate_modification(modification)
    return '', 200


@app.route('/disable', methods=['POST'])
def disable():
    global disabled
    disabled = True
    hc.stop_checking_leader()
    hc.stop_sending_heartbeats()
    return '', 200


@app.route('/enable', methods=['POST'])
def enable():
    global disabled
    disabled = False
    return '', 200


app.run(host='0.0.0.0', port=ports[idx])
