import argparse
from collections import deque, Counter, defaultdict
import gym
import numpy as np
import os
from tqdm import tqdm
from tensorboardX import SummaryWriter
import tensorflow as tf

from rlpack.algos import DQN

from utils import AgentWrapper


parser = argparse.ArgumentParser(description="Parse environment name.")
parser.add_argument("--gpu", type=str, default="0")
parser.add_argument("--port", type=int, default=50000)
parser.add_argument("--env", type=str, default="PongNoFrameskip-v4")
args = parser.parse_args()

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

agent_wrapper = AgentWrapper(port=50000)
agent_wrapper.start()


nb_actions = 6
OBS_SHAPE = (84, 84, 4)
LOG_PATH = f"./log/dqn_atari/Pong"


class Memory(object):
    def __init__(self, capacity: int, dim_obs, dim_act, statetype=np.uint8):
        self._state = np.zeros((capacity, *dim_obs), dtype=statetype)
        self._action = np.zeros(capacity, dtype=np.int32)
        self._reward = np.zeros(capacity, dtype=np.float32)
        self._done = np.zeros(capacity, dtype=np.float32)
        self._next_state = np.zeros((capacity, *dim_obs), dtype=statetype)

        self._size = 0
        self._capacity = capacity

    def store_sard(self, s_list, a_list, r_list, d_list):

        for s_batch, a_batch, r_batch, d_batch in zip(s_list, a_list, r_list, d_list):
            ind = self._size % self._capacity
            t = len(d_batch)
            if ind + t <= self._capacity:
                self._state[ind: ind+t, ...] = np.asarray(s_batch)[:-1, ...]
                self._action[ind: ind+t] = np.asarray(a_batch)
                self._reward[ind: ind+t] = np.asarray(r_batch)
                self._done[ind: ind+t] = np.asarray(d_batch)
                self._next_state[ind: ind+t, ...] = np.asarray(s_batch)[1:, ...]
            else:
                d = self._capacity - ind
                self._state[ind:, ...] = np.asarray(s_batch[:d])
                self._action[ind:] = np.asarray(a_batch[:d])
                self._reward[ind:] = np.asarray(r_batch[:d])
                self._done[ind:] = np.asarray(d_batch[:d])
                self._next_state[ind:, ...] = np.asarray(s_batch[1:d+1])

                n = t - d
                self._state[:n, ...] = np.asarray(s_batch[d:])
                self._action[:n] = np.asarray(a_batch[d:])
                self._reward[:n] = np.asarray(r_batch[d:])
                self._done[:n] = np.asarray(d_batch[d:])
                self._next_state[:n, ...] = np.asarray(s_batch[d+1:])
            self._size += t

    def sample(self, n: int):
        n_sample = self._size if self._size < self._capacity else self._capacity
        inds = np.random.randint(n_sample, size=n)
        state_batch = self._state[inds, ...]
        action_batch = self._action[inds]
        reward_batch = self._reward[inds]
        done_batch = self._done[inds]
        next_state_batch = self._next_state[inds, ...]
        return state_batch, action_batch, reward_batch, done_batch, next_state_batch


def obs_fn():
    obs = tf.placeholder(shape=[None, *OBS_SHAPE], dtype=tf.uint8, name="observation")
    obs = tf.to_float(obs) / 255.0
    return obs


def value_fn(obs):
    x = tf.layers.conv2d(obs, filters=32, kernel_size=8, strides=4, activation=tf.nn.relu)
    x = tf.layers.conv2d(obs, filters=64, kernel_size=4, strides=2, activation=tf.nn.relu)
    x = tf.layers.conv2d(obs, filters=64, kernel_size=3, strides=1, activation=tf.nn.relu)
    x = tf.layers.flatten(x)
    x = tf.layers.dense(x, units=256, activation=tf.nn.relu)
    x = tf.layers.dense(x, units=nb_actions)
    return x


def main():
    agent = DQN(obs_fn=obs_fn,
                value_fn=value_fn,
                dim_act=nb_actions,
                update_target_freq=1000,
                log_freq=100,
                save_path=LOG_PATH,
                lr=2.5e-4,
                epsilon_schedule=lambda x: max(0.1, (1e5-x) / 1e5),
                train_epoch=1)
    mem = Memory(capacity=int(1e6), dim_obs=OBS_SHAPE, dim_act=nb_actions)
    sw = SummaryWriter(log_dir=LOG_PATH)

    t = 0
    totrew = defaultdict(int)
    printrew = deque(maxlen=20)
    while True:
        for i in tqdm(range(10)):
            env_ids, states, rewards, dones = agent_wrapper.get_srd_batch(
                batchsize=16)

            actions = agent.get_action(np.asarray(states))
            agent_wrapper.put_a_batch(env_ids, actions)

            for i, env_id in enumerate(env_ids):
                totrew[env_id] += rewards[i]
                if dones[i] is True:
                    printrew.append(totrew[env_id])
                    totrew[env_id] = 0

        s_list, a_list, r_list, d_list = agent_wrapper.get_episodes(withdraw_running=True)
        mem.store_sard(s_list, a_list, r_list, d_list)

        meanrew = np.mean(printrew)
        print(f"{t}th reward:", meanrew)
        t += 1
        sw.add_scalars("dqn", {"totrew": meanrew}, global_step=t)

        print("s:", [len(x) for x in s_list])
        print("a:", [len(x) for x in a_list])
        print("r:", [len(x) for x in r_list])
        print("d:", [len(x) for x in d_list])

        for i in tqdm(range(2)):
            agent.update(mem.sample(64))


if __name__ == "__main__":
    main()
