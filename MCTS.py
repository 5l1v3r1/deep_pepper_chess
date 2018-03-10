import numpy as np

#this is hypothetical functions and classes that should be created by teamates.
import chess.uci
from policy_network import PolicyValNetwork_Full
import value_network
from chess_env import ChessEnv
import stockfish_eval
from features import BoardToFeature
import config


def game_over(state):
    if chess.is_game_over(state):

        score = chess.results(state)
        if score == 0:
            return True, -1
        if score == 0.5:
            return True, 0
        if score == 0:
            return True, -1

    else:
        return False, None


def resignation(state):
    stockfish_eval = stockfish_eval(state)
    if abs(stockfish_eval) > 6.5:
        return True, stockfish_eval / abs(stockfish_eval)
    return False, None

def state_visited(state_list,state):
    if not state_list:
        return False, None
    for i in range(len(state_list)):
        if  np.array_equal(state_list[i].board, state):
            return True, i
    return False, None

def Q(N,W):
    return W/float(N)

class Leaf(object):

    #This class inherit the Board class which control the board representation, find legale move and next board represenation.
    #It has the ability to store and update for each leaf the number of state-action N(s,a), Q(s,a) and P(s,a)
    def __init__(self, env:ChessEnv, init_W, init_N,init_P, explore_factor):
            assert init_N.shape == (4096,)
            assert init_W.shape == (4096,)
            assert init_P.shape == (4096,)
            self.env = env
            self.P = init_P
            self.N = init_N 
            self.W = init_W
            self.explore_factor = explore_factor

    @property
    def Q(self):
        return np.divide(self.W,self.N)

    @property
    def U(self):
        return np.multiply( np.multiply( self.explore_factor , self.P) , np.divide( np.sqrt(np.sum(self.N)),(np.add(1., self.N))))

    def best_action(self):
        index = np.argmax(np.add(self.U, self.Q)) #U and Q are lists of dimensionality no.of legal moves
        # it is nice to decorate the legal move method with property
        return index

    @property
    def next_board(self):
        best_index = self.best_action
        mymove = config.INDEXTOMOVE[best_index]
        self.env.step(mymove)
        return self.env.board
        #return self.render_action(self.board, self.best_action)#assuming the function you did
        #Do chess.Move()

    def N_update(self,action_index):
        self.N[action_index]+=1

    def W_update(self, V_next, action_index):
        self.W[action_index]+=V_next

    def P_update(self, new_P):
        self.P = new_P

def legal_mask(board,all_move_probs):
    legal_moves = board.legal_moves
    mask = np.zeros_like(all_move_probs)
    total_p = 0
    for legal_move in legal_moves:
        legal_move_uci = legal_move.uci()
        ind = config.MOVETOINDEX[legal_move_uci]
        mask[ind] = 1
        all_move_probs += 1e-6
        total_p += all_move_probs[ind]
    
    legal_moves_prob =  np.multiply(mask,all_move_probs) 
    legal_moves_prob = np.divide(legal_moves_probs,total_p)
    return p_legal_moves
    
#state type and shape does not matter

def MCTS(env: ChessEnv, init_W, init_N, explore_factor,temp,network: PolicyValNetwork_Full,dirichlet_alpha):#we can add here all our hyper-parameters
    # Monte-Carlo tree search function corresponds to the simulation step in the alpha_zero algorithm
    # argumentes: state: the root state from where the stimulation start. A board.
    #             explore_factor: hyper parameter to tune the exploration range in UCT
    #             temp: temperature constant for the optimum policy to control the level of exploration in the Play policy
    #             optional : dirichlet noise
    #             alpha_prob: current policy-network
    #             alpha_eval: current value-network
    #             dirichlet_alpha: alpha parameter for the dirichlet process
    
    # return: pi: vector of policy(action) with the same shape of legale move. Shape: 4096x1

    #history of leafs for all previous runs
    env_copy = env.copy()
    state = env.board
    state_copy = state.copy()
    leafs=[]
    for simulation in range (800):
        curr_env = env.copy()
        state_action_list=[] #list of leafs in the same run
        moves = 0
        RESIGN = False
        while not game_over(curr_env.board)[0] and not RESIGN:

            moves += 0.5
            if moves >30 and not moves%10:
                RESIGN = resignation(curr_env.board)[0]
            
            visited, index = state_visited(leafs,state_copy)
            if visited:
                state_action_list.append(leafs[index])
            else: # if state unvisited get legal moves probabilities using policy network
                giraffe_features = BoardToFeature(curr_env.board)
                all_move_probs, _ = network.forward(giraffe_features)
                legal_move_probs = legal_mask(curr_env.board,all_move_probs)
                state_action_list.append(Leaf(curr_env, init_W, legal_move_probs, init_N, explore_factor))
                leafs.append(state_action_list[-1])
            #if leafs length is exactly 1 this mean we are in the root state then we should appy the dirichlet noise
            #(check alphago zero paper page 24)
            if len(leafs) == 1:
                leafs[0].P = np.add(np.multiply((1 - epsilon),leafs[0].P), np.multiply(epsilon, np.random.dirichlet(dirichlet_alpha, len(leaf[0].P))))
            best_action = config.INDEXTOMOVE[leaf[-1].best_action]
            curr_env = curr_env.step(best_action)


        for i in list(reversed(range(len(state_action_list)))):
            action_index = state_action_list[i].best_action #always legal since best_action
            state_action_list[i].N_update(action_index)
            if (i == len(state_action_list)-1):
                game_over_check, end_score = game_over(curr_env.board)
                resign_check, resign_score = resignation(curr_env.board)
                if game_over_check:
                    state_action_list[i].W_update(end_score, action_index)
                elif (resign_check):
                    state_action_list[i].W_update(resign_score, action_index)
            else:
                giraffe_features = BoardToFeature(state_action_list[i+1].board)
                _, state_value_prediction = network.forward(giraffe_features)
                state_action_list[i].W_update( state_value_prediction, action_index)
 
    N = leafs[0].N

    norm_factor = np.sum(np.power(N,temp))
    #optimum policy
    pi = np.divide(np.power(N,temp),norm_factor)

    return pi