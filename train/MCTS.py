import time
import numpy as np
import torch

from config import Config
from game.chess_env import ChessEnv
from game.features import board_to_feature
from network.policy_network import PolicyValNetwork_Giraffe
from game.stockfish import Stockfish
stockfish = Stockfish()
class Node(object):
    ''' Represent and store statistics of each node in the search tree.
    #arguments: 
        ChessEnv: Chess env object,
        explore_factor: float number used as hyperparameter to control  range of exploration ,
        init_W: initial cumulative value function 'W',
        init_N: initial visit action counter, 
        init_P: inital probability distribution for actions space,
        parent: parent node which is another instance of the class Node,
        child_id = best child index. 
    '''
    
    def __init__(self, env: ChessEnv, explore_factor,
                 init_W=np.zeros((Config.d_out,)),
                 init_N=np.zeros((Config.d_out,)),
                 init_P=np.ones((Config.d_out,)) * (1 / Config.d_out),
                 parent=None,
                 child_id=None):
        assert init_N.shape == (Config.d_out,)
        assert init_W.shape == (Config.d_out,)
        assert init_P.shape == (Config.d_out,)

        self.env = env

        self.parent = parent

        self.explore_factor = explore_factor

        legal_moves = env.board.legal_moves
        self.legal_move_inds = []
        self.legal_moves = []

        for move in legal_moves:
            legal_move_uci = move.uci()
            ind = Config.MOVETOINDEX[legal_move_uci]
            self.legal_moves.append(legal_move_uci)
            self.legal_move_inds.append(ind)
        self.P = init_P[self.legal_move_inds]
        self.N = init_N[self.legal_move_inds]
        self.W = init_W[self.legal_move_inds]
        self.child_id = child_id
        self.children = None

    @property
    def Q(self):
        with np.errstate(divide='ignore', invalid='ignore'):
            Q = np.divide(self.W, self.N)
        Q[np.isnan(Q)] = 0
        return Q

    @property
    def U(self):
        return np.multiply(np.multiply(self.explore_factor, self.P),
                           np.divide(np.sqrt(np.sum(self.N)), (np.add(1., self.N))))

    def select_best_child(self):
        if self.env.white_to_move:
            move_UCT = (np.add(self.U, self.Q))
        else:
            move_UCT = (np.add(self.U, -self.Q))

        max_list = np.argwhere(move_UCT == np.amax(move_UCT))
        child_id = int(max_list[np.random.randint(0, len(max_list))])
        move = self.legal_moves[child_id]
        self.taken_action = move
        if self.children[child_id] is None:
            next_env = self.env.copy()
            next_env.step(move)
            self.children[child_id] = Node(next_env, self.explore_factor, parent=self, child_id=child_id)

        return self.children[child_id]

    def expand(self, network):
        self.children = [None] * len(self.legal_moves)
        all_move_probs, v = network.forward(torch.from_numpy(board_to_feature(self.env.board)).unsqueeze(0))
        #v = stockfish.stockfish_eval(self.env.board,10)
        all_move_probs = all_move_probs.squeeze().data.numpy()
        child_probs = (all_move_probs[self.legal_move_inds] + 1e-12) / np.sum(all_move_probs[self.legal_move_inds] + 1e-12)
        child_probs = np.exp(child_probs)
        self.P = child_probs
        self.value = v

    def N_update(self, action_index):
        self.N[action_index] += 1

    def W_update(self, V_next, action_index):
        self.W[action_index] += V_next

    def add_dirichlet(self):
        num_legal_moves = len(self.legal_move_inds) + 1
        d_noise = np.random.dirichlet(Config.D_ALPHA * np.ones(self.P.shape))
        self.P = np.add(self.P, d_noise)
        self.P = self.P / self.P.sum(keepdims=1)


def legal_mask(board, all_move_probs) -> np.array:
    legal_moves = board.legal_moves
    mask = np.zeros_like(all_move_probs)
    total_p = 0
    inds = []
    for legal_move in legal_moves:
        legal_move_uci = legal_move.uci()
        ind = Config.MOVETOINDEX[legal_move_uci]
        mask[ind] = 1
        inds.append(ind)
        total_p += all_move_probs[ind]

    legal_moves_prob = np.multiply(mask, all_move_probs)

    legal_moves_prob = np.divide(legal_moves_prob, total_p)

    return legal_moves_prob

def MCTS(temp: float,
         network: PolicyValNetwork_Giraffe,
         root,
         dirichlet_alpha=Config.D_ALPHA,
         batch_size: int = Config.BATCH_SIZE) -> tuple:
    """
    Monte-Carlo tree search function corresponds to the simulation step in the alpha_zero algorithm
    arguments: state: the root state from where the stimulation start. A board.

    :param temp: temperature constant for the optimum policy to control the level of exploration/
    :param network: policy network for evaluation
    :param explore_factor: hyper parameter to tune the exploration range in UCT
    :param dirichlet_alpha: alpha parameter for the dirichlet process
    :param epsilon: parameter for exploration using dirichlet noise
    :param batch_size:
    :return: return: pi: vector of policy(action) with the same shape of legale move. Shape: 4096x1
    """
    mcts_start = time.time()
    if not root.children:
        root.expand(network)
    root.add_dirichlet()
    avg_backup_time = 0.
    avg_expand_time = 0.
    avg_select_time = 0.
    for simulation in range(Config.NUM_SIMULATIONS):
        start_time = time.time()
        curr_node, moves, game_over, z = select(root)
        avg_select_time += (time.time() - start_time) / Config.NUM_SIMULATIONS
        start_time = time.time()
        leaf = expand_and_eval(curr_node, network, game_over, z, moves)
        avg_expand_time += (time.time() - start_time) / Config.NUM_SIMULATIONS
        start_time = time.time()
        backup(leaf, root)
        avg_backup_time += (time.time() - start_time) / Config.NUM_SIMULATIONS
    N = root.N
    norm_factor = np.sum(np.power(N, temp))

    pi = np.divide(np.power(N, temp), norm_factor)
    action_index = np.argmax(pi)

    new_pi = np.zeros(Config.d_out, )
    new_pi[root.legal_move_inds] = pi
    return new_pi, root.children[action_index], root


########################
######## Select ########
########################
# Traverses from root node to leaf node using UCB selection
def select(root_node):
    '''
    Selection phase function. It is the first part of the MCTS process. The selection is done according to the UCB score.
    It stops when reaching a leaf node.
    : param root_node the nest object root_node which stores the stats of the whole descendent tree.
    :return the last node before the leaf node(object), number of selectiom moves(int), game_over (bool) and the score if 
            game over is true ( float).
    
    '''
    curr_node = root_node
    moves = 0
    game_over, z = curr_node.env.is_game_over(moves)

    while curr_node.children:
        curr_node = curr_node.select_best_child()
        moves += 1
    game_over, z = curr_node.env.is_game_over(moves)

    return curr_node, moves, game_over, z


##########################
### Expand and evaluate###
##########################
# Once at a leaf node expand using the network
def expand_and_eval(node, network, game_over, z, moves):
    '''
    find all  children considering all legal moves
    :param node: leaf node
    :param network: neural network model used to evaluate the leaf node value
    :param game_over: boolean  variable to avoid expanding when the game is over
    :param z: the game score if game is over
    :param moves: number of moves in the last selection phase.
    :return expanded node
    '''
    if game_over:
        node.value = z
        return node
    node.expand(network)
    return node


###############
### Back-up ###
###############
'''
Update the the total value function and state action counter for each node encoutered during the selection phase.
'''
def backup(leaf_node, root_node):
    child_node = leaf_node
    v = 20.0 * leaf_node.value
    parent_node = leaf_node.parent
    if not parent_node:
        return leaf_node

    while child_node != root_node:
        parent_node.N_update(child_node.child_id)
        parent_node.W_update(v, child_node.child_id)
        child_node = parent_node
        parent_node = parent_node.parent
