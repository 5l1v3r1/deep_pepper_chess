# import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from config import Config


# from torch.autograd import Variable
# fully connected (including the first layer to hidden layer neurons. so, this is different from giraffe network) network with 2 hidden layers.

class Critic_Giraffe(nn.Module):
    def __init__(self,
            pretrain = False,
            d_in = Config.d_in,
            gf = Config.global_features,
            pc = Config.piece_centric,
            sc = Config.square_centric,
            h1a = Config.h1a,
            h1b = Config.h1b,
            h1c = Config.h1c,
            h2 = Config.h2,
            d_out = Config.d_out,
            eval_out=1):
        "We instantiate various modules"
        super(Critic_Giraffe, self).__init__()
        self.gf = gf
        self.pc = pc
        self.sc = sc
        self.linear1a = nn.Linear(gf, h1a)
        self.linear1b = nn.Linear(pc, h1b)
        self.linear1c = nn.Linear(sc, h1c)
        self.linear2 = nn.Linear(h1a + h1b + h1c, h2)
        self.linear3 = nn.Linear(h2, eval_out)

    def forward(self, x):
        x = Variable(x.float())
        "Here, we can use modules defined in the constrcutor (__init__ part defined above) as well as arbitrary operators on Variables"
        gf = self.gf
        pc = self.pc
        sc = self.sc

        x1 = x[:, 0:gf]
        x2 = x[:, gf:gf + pc]
        x3 = x[:, gf + pc:gf + pc + sc]

        h1a_relu = F.relu(self.linear1a(x1))
        h1b_relu = F.relu(self.linear1b(x2))
        h1c_relu = F.relu(self.linear1c(x3))
        h1_relu = torch.cat((h1a_relu, h1b_relu, h1c_relu), dim=1)
        h2_relu = F.relu(self.linear2(h1_relu))
        val_out = F.Tanh(self.linear3(h2_relu))

        return val_out


class Critic_FCGiraffe(nn.Module):
    def __init_(self, d_in, h1, h2, eval_out=1):
        super(Critic_FCGiraffe, self).__init__()
        self.linear1 = nn.Linear(d_in, h1)
        self.linear2 = nn.Linear(h1, h2)
        self.linear3 = nn.Linear(h2, eval_out)

    def forward(self, x):
        "Here, we will use modules defined in the constructor (__init__ part defined above) as well as arbitray operators on Variables"
        h1_relu = F.relu(self.linear1(x))

        h2_relu = F.relu(self.linear2(h1_relu))
        v_out = F.Tanh(self.linear3(h2_relu))

        return v_out
