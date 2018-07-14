#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 12 11:09:51 2018

@author: sadra
"""

import numpy as np

from auxilary_methods import find_mode
from controller import control_vanilla

def simulate_vanilla(s,x):
    t=0
    while t<100:
        print("state:",x.T)
        u=control_vanilla(s,x)
        if u==False:
            return
        print("control:",u.T)
        x=evolve(s,x,u)
    
def evolve(s,x,u):
    i=find_mode(s,x)
    print("x=",x.T,"u=",u,"i=",i,"\n")
    return np.dot(s.A[i],x)+np.dot(s.B[i],u)+s.c[i]#+(np.random.random((2,1))-0.5)*0.00001