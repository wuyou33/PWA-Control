# -*- coding: utf-8 -*-
"""
Created on Tue Dec  4 15:21:17 2018

@author: sadra
"""

import numpy as np
import scipy as sp
from gurobipy import Model,GRB,LinExpr,QuadExpr,tuplelist

import time as time

from pypolycontain.lib.containment_encodings import subset_LP,subset_zonotopes,subset_generic
from pypolycontain.lib.polytope import polytope
from pypolycontain.lib.zonotope import zonotope
from pypolycontain.lib.AH_polytope import cartesian_product


def point_trajectory_sPWA(system,x0,list_of_goals,T,eps=0,optimize_controls_indices=[]):
    """
    Description: point Trajectory Optimization
    Inputs:
        system: control system in the form of sPWA
        x_0: initial point
        T= trajectory length
        list_of_goals: reaching one of the goals is enough. Each goal is a zonotope
        eps= vector, box for how much freedom is given to deviate from x_0 in each direction
    Method:
        Uses convexhull formulation
    """
    t_start=time.time()
    model=Model("Point Trajectory Optimization")
    x=model.addVars(range(T+1),range(system.n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x")
    u=model.addVars(range(T),range(system.m),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u")
    ##
    x_PWA=model.addVars([(t,n,i,j) for t in range(T+1) for n in system.list_of_sum_indices \
                         for i in system.list_of_modes[n] for j in range(system.n)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x_pwa")
    u_PWA=model.addVars([(t,n,i,j) for t in range(T) for n in system.list_of_sum_indices \
                         for i in system.list_of_modes[n] for j in range(system.m)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_pwa")
    delta_PWA=model.addVars([(t,n,i) for t in range(T) for n in system.list_of_sum_indices \
                             for i in system.list_of_modes[n]],vtype=GRB.BINARY,name="delta_pwa")
    model.update()
    
    # Initial Condition    
    print "inside function epsilon is",eps,"initial",x0.T
    for j in range(system.n):
#        model.addConstr(x[0,j]<=x0[j,0]+eps*system.scale[j])
#        model.addConstr(x[0,j]>=x0[j,0]-eps*system.scale[j])
         model.addConstr(x[0,j]==x0[j,0])
    
    # Convexhull Dynamics
    model.addConstrs(x[t,j]==x_PWA.sum(t,n,"*",j) for t in range(T+1) for j in range(system.n)\
                     for n in system.list_of_sum_indices)
    model.addConstrs(u[t,j]==u_PWA.sum(t,n,"*",j) for t in range(T) for j in range(system.m)\
                     for n in system.list_of_sum_indices)
    for t in range(T):
        for n in system.list_of_sum_indices:
            for i in system.list_of_modes[n]:
                for j in range(system.C[n,i].H.shape[0]):
                    expr=LinExpr()
                    expr.add(LinExpr([(system.C[n,i].H[j,k],x_PWA[t,n,i,k]) for k in range(system.n)]))
                    expr.add(LinExpr([(system.C[n,i].H[j,k+system.n],u_PWA[t,n,i,k]) for k in range(system.m)])) 
                    model.addConstr(expr<=system.C[n,i].h[j,0]*delta_PWA[t,n,i])
    # Dynamics
    for t in range(T):
        for j in range(system.n):
            expr=LinExpr()
            for n in system.list_of_sum_indices:
                expr.add(LinExpr([(system.c[n,i][j,0],delta_PWA[t,n,i]) for i in system.list_of_modes[n]]))
                expr.add(LinExpr([(system.A[n,i][j,k],x_PWA[t,n,i,k]) for k in range(system.n) \
                    for i in system.list_of_modes[n]]))
                expr.add(LinExpr([(system.B[n,i][j,k],u_PWA[t,n,i,k]) for k in range(system.m) \
                    for i in system.list_of_modes[n]]))
            model.addConstr(x[t+1,j]==expr)
    # Integer Variables
    for t in range(T):
        for n in system.list_of_sum_indices:
            expr=LinExpr([(1.0,delta_PWA[t,n,i]) for i in system.list_of_modes[n]])
            model.addConstr(expr==1)
    # Final Goal Constraints
    mu=model.addVars(list_of_goals,vtype=GRB.BINARY,name="mu")
    _p=model.addVars(tuplelist([(goal,j) for goal in list_of_goals for j in range(goal.G.shape[1])]),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="p")
    model.update()
    for j in range(system.n):
        L=LinExpr()
        L.add(LinExpr([(goal.G[j,k],_p[goal,k]) for goal in list_of_goals for k in range(goal.G.shape[1])]))
        L.add(LinExpr([(goal.x[j,0],mu[goal]) for goal in list_of_goals]))
        model.addConstr(L==x[T,j])
    model.addConstr(mu.sum()==1)
    for goal in list_of_goals:
        for j in range(goal.G.shape[1]):
            model.addConstr(_p[goal,j]<=mu[goal])
            model.addConstr(-_p[goal,j]<=mu[goal])
    # Cost Engineering
    print "model built in",time.time()-t_start," seconds"
    # Optimize
    model.write("point_trajectory.lp")
    J=QuadExpr(sum([u[t,j]*u[t,j] for j in optimize_controls_indices for t in range(T)]))
    model.setParam("MIPfocus",0)
    model.setObjective(J,GRB.MINIMIZE)
    model.setParam('TimeLimit', 60)
    model.optimize()
    if model.Status==9 and model.SolCount>=1:
        flag=True # Some Solution
        print "time limit reached but %d solutions exist"%model.SolCount
    elif model.Status==9 and model.SolCount==0:
        flag=False # No solution
        print "time limit reached and no solution exists"
    elif model.Status not in [2,11]:
        flag=False
    else:
        flag=True
    if flag==False:
        print "Infeasible or time limit reached"
        return (x,u,delta_PWA,mu,False)
    else:
        u_num,x_num,delta_PWA_num,mu_num={},{},{},{}
        for t in range(T+1):
            x_num[t]=np.array([x[t,i].X for i in range(system.n)]).reshape(system.n,1)
        for t in range(T):
            u_num[t]=np.array([u[t,i].X for i in range(system.m)]).reshape(system.m,1)
        for t in range(T):
            for n in system.list_of_sum_indices:
                for i in system.list_of_modes[n]:
                    delta_PWA_num[t,n,i]=delta_PWA[t,n,i].X
        for goal in list_of_goals:
            mu_num[goal]=mu[goal].X
        return (x_num,u_num,delta_PWA_num,mu_num,True)



def point_trajectory_tishcom(system,x0,list_of_goals,T,eps=0,optimize_controls_indices=[],cost=2,time_limit=120):
    """
    Description: point Trajectory Optimization
    Inputs:
        system: control system from hard contact time-stepping with convex hull method
        x_0: initial point
        T= trajectory length
        list_of_goals: reaching one of the goals is enough. Each goal is an AH_polytope
        eps= vector, box for how much freedom is given to deviate from x_0 in each direction
    Method:
        Uses convexhull formulation
    """
    t_start=time.time()
    model=Model("Point Trajectory Optimization using TISHCOM Formulation")
    x=model.addVars(range(T+1),range(system.n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x")
    u=model.addVars(range(T),range(system.m_u),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u")
    u_lambda=model.addVars(range(T),range(system.m_lambda),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_lambda")
    mu=model.addVars(list_of_goals,vtype=GRB.BINARY,name="mu")
    _p=model.addVars(tuplelist([(goal,j) for goal in list_of_goals for j in range(goal.G.shape[1])]),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="p")
    ## tau, T Variables
    x_time=model.addVars(range(T+1),system.Eta,range(system.n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x_t")
    u_time=model.addVars(range(T),system.Eta,range(system.m_u),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_t")
    u_lambda_time=model.addVars(range(T),system.Eta,range(system.m_lambda),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="lambda_t")
    delta_time=model.addVars(range(T),system.Eta,vtype=GRB.BINARY,name="delta_t")    
    ## TISCHOM Variables
    x_TISHCOM=model.addVars([(t,tau,i,sigma,j) for t in range(T) for tau in system.Eta for i in system.list_of_contact_points \
                         for sigma in i.Sigma for j in range(system.n)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x_TISHCOM")
    u_TISHCOM=model.addVars([(t,tau,i,sigma,j) for t in range(T) for tau in system.Eta for i in system.list_of_contact_points \
                         for sigma in i.Sigma for j in range(system.m_u)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_TISHCOM")
    lambda_TISHCOM=model.addVars([(t,tau,i,sigma,j) for t in range(T) for tau in system.Eta for i in system.list_of_contact_points \
                         for sigma in i.Sigma for j in range(system.m_lambda)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="lambda_TISCHOM")
    delta_TISHCOM=model.addVars([(t,tau,i,sigma) for t in range(T) for tau in system.Eta for i in system.list_of_contact_points \
                         for sigma in i.Sigma],vtype=GRB.BINARY,name="delta_TISHCOM")
    model.update()
    # Initial Condition    
    print "epsilon is",eps,"initial condition:",x0.T
    for j in range(system.n):
        model.addConstr(x[0,j]<=x0[j,0]+eps*system.scale[j])
        model.addConstr(x[0,j]>=x0[j,0]-eps*system.scale[j])
#         model.addConstr(x[0,j]==x0[j,0])
 
    # Equation a: Mode Constaints
    for t in range(T):
        for tau in  system.Eta:
            for i in system.list_of_contact_points:
                for sigma in i.Sigma:
                    for row in range(system.E[tau][i][sigma].shape[0]):
#                        print tau,i,sigma,row,[system.E[tau][i][sigma][row,k] for k in range(system.n) ]
                        a_x=LinExpr([(system.E[tau][i][sigma][row,k],x_TISHCOM[t,tau,i,sigma,k]) for k in range(system.n)])
                        a_u=LinExpr([(system.E[tau][i][sigma][row,k+system.n],u_TISHCOM[t,tau,i,sigma,k])  for k in range(system.m_u)])
                        a_lambda=LinExpr([(system.E[tau][i][sigma][row,k+system.n+system.m_u],lambda_TISHCOM[t,tau,i,sigma,k]) for k in range(system.m_lambda)])
                        model.addConstr(a_x+a_u+a_lambda <= system.e[tau][i][sigma][row,0]*delta_TISHCOM[t,tau,i,sigma])
                        
    # Equation b: Convexhull Dynamics
    model.addConstrs(x_time[t,tau,j]==x_TISHCOM.sum(t,tau,i,"*",j) for t in range(T) for tau in system.Eta \
                                         for i in  system.list_of_contact_points for j in range(system.n))
    model.addConstrs(u_time[t,tau,j]==u_TISHCOM.sum(t,tau,i,"*",j) for t in range(T) for tau in system.Eta \
                                         for i in  system.list_of_contact_points for j in range(system.m_u))
    model.addConstrs(u_lambda_time[t,tau,j]==lambda_TISHCOM.sum(t,tau,i,"*",j) for t in range(T) for tau in system.Eta \
                                         for i in  system.list_of_contact_points for j in range(system.m_lambda))
    model.addConstrs(delta_time[t,tau]==delta_TISHCOM.sum(t,tau,i,"*") for t in range(T) for tau in system.Eta \
                                         for i in  system.list_of_contact_points)
    
    # Equation c: Evolution
    for t in range(T):
        for row in range(system.n):
            a_x=LinExpr([(system.A[tau][row,k],x_time[t,tau,k]) for tau in system.Eta for k in range(system.n)])
            a_u=LinExpr([(system.B_u[tau][row,k],u_time[t,tau,k]) for tau in system.Eta for k in range(system.m_u)])
            a_lambda=LinExpr([(system.B_lambda[tau][row,k],u_lambda_time[t,tau,k]) for tau in system.Eta for k in range(system.m_lambda)])
            a_c=LinExpr([(system.c[tau][row,0],delta_time[t,tau]) for tau in system.Eta])
            model.addConstr(x[t+1,row]==a_x+a_u+a_lambda+a_c)
    
    # Equation d: For tau: the environments
    model.addConstrs(x[t,j]==x_time.sum(t,"*",j) for t in range(T) for j in range(system.n))
    model.addConstrs(u[t,j]==u_time.sum(t,"*",j) for t in range(T) for j in range(system.m_u))
    model.addConstrs(u_lambda[t,j]==u_lambda_time.sum(t,"*",j) for t in range(T) for j in range(system.m_lambda))
    model.addConstrs(1==delta_time.sum(t,"*") for t in range(T))
    
    # Goal Constraints
    for j in range(system.n):
        L=LinExpr()
        L.add(LinExpr([(goal.G[j,k],_p[goal,k]) for goal in list_of_goals for k in range(goal.G.shape[1])]))
        L.add(LinExpr([(goal.x[j,0],mu[goal]) for goal in list_of_goals]))
        model.addConstr(L==x[T,j])
    model.addConstr(mu.sum("*")==1)
    for goal in list_of_goals:
        for j in range(goal.G.shape[1]):
            model.addConstr(_p[goal,j]<=mu[goal])
            model.addConstr(-_p[goal,j]<=mu[goal])
    # Cost Engineering
    print "model built in",time.time()-t_start," seconds"
    # Optimize
    model.write("point_trajectory_time_stepping.lp")
    model.setParam("MIPfocus",1)
    model.setParam('TimeLimit', 6)
    if cost==2:
        J=QuadExpr(sum([u[t,j]*u[t,j] for j in optimize_controls_indices for t in range(T)]))
        model.setObjective(J,GRB.MINIMIZE)
        model.setParam('TimeLimit', time_limit)
        model.optimize()
    elif cost==1:
        u_abs=model.addVars(range(T),optimize_controls_indices,obj=1)
        model.update()
        model.addConstrs(u[t,j]<=u_abs[t,j] for t in range(T) for j in optimize_controls_indices)
        model.addConstrs(-u[t,j]<=u_abs[t,j] for t in range(T) for j in optimize_controls_indices)
        model.optimize()
    else:
        model.optimize()
    x_n={t:np.array([x[t,i].X for i in range(system.n)]) for t in range(T+1)}
    u_n={t:np.array([u[t,i].X for i in range(system.m_u)]) for t in range(T)}
    lambda_n={t:np.array([u_lambda[t,i].X for i in range(system.m_lambda)]) for t in range(T)}
    mode_n={}
    for t in range(T):
        mode_n[t]=[None]*len(system.list_of_contact_points)
        for tau in system.Eta:
            for i in system.list_of_contact_points:
                for sigma in i.Sigma:
                    if np.linalg.norm(delta_TISHCOM[t,tau,i,sigma].X-1)<=10**-1:
                        mode_n[t][i.index]=sigma
        mode_n[t]=tuple(mode_n[t])
    print "*"*80
    return x_n,u_n,lambda_n,mode_n
            

def point_trajectory_tishcom_time_varying(system,list_of_environemnts,x0,list_of_goals,T,eps=0,optimize_controls_indices=[],cost=2,time_limit=120):
    """
    Description: point Trajectory Optimization
    Inputs:
        system: control system from hard contact time-stepping with convex hull method
        x_0: initial point
        T= trajectory length
        list_of_goals: reaching one of the goals is enough. Each goal is an AH_polytope
        eps= vector, box for how much freedom is given to deviate from x_0 in each direction
    Method:
        Uses convexhull formulation
    """
    t_start=time.time()
    model=Model("Point Trajectory Optimization using TISHCOM Formulation")
    x=model.addVars(range(T+1),range(system.n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x")
    u=model.addVars(range(T),range(system.m_u),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u")
    u_lambda=model.addVars(range(T),range(system.m_lambda),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_lambda")
    mu=model.addVars(list_of_goals,vtype=GRB.BINARY,name="mu")
    _p=model.addVars(tuplelist([(goal,j) for goal in list_of_goals for j in range(goal.G.shape[1])]),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="p")
    ## tau, T Variables
#    x_time=model.addVars(range(T+1),system.Eta,range(system.n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x_t")
#    u_time=model.addVars(range(T),system.Eta,range(system.m_u),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_t")
#    u_lambda_time=model.addVars(range(T),system.Eta,range(system.m_lambda),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="lambda_t")
#    delta_time=model.addVars(range(T),system.Eta,vtype=GRB.BINARY,name="delta_t")    
    ## TISCHOM Variables
    x_TISHCOM=model.addVars([(t,i,sigma,j) for t in range(T) for i in system.list_of_contact_points \
                         for sigma in i.Sigma for j in range(system.n)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x_TISHCOM")
    u_TISHCOM=model.addVars([(t,i,sigma,j) for t in range(T) for i in system.list_of_contact_points \
                         for sigma in i.Sigma for j in range(system.m_u)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_TISHCOM")
    lambda_TISHCOM=model.addVars([(t,i,sigma,j) for t in range(T) for i in system.list_of_contact_points \
                         for sigma in i.Sigma for j in range(system.m_lambda)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="lambda_TISCHOM")
    delta_TISHCOM=model.addVars([(t,i,sigma) for t in range(T) for i in system.list_of_contact_points \
                         for sigma in i.Sigma],vtype=GRB.BINARY,name="delta_TISHCOM")
    model.update()
    # Initial Condition    
    print "epsilon is",eps,"initial condition:",x0.T
    for j in range(system.n):
        model.addConstr(x[0,j]<=x0[j,0]+eps*system.scale[j])
        model.addConstr(x[0,j]>=x0[j,0]-eps*system.scale[j])
#         model.addConstr(x[0,j]==x0[j,0])
 
    # Equation a: Mode Constaints
    for t in range(T):
        tau=list_of_environemnts[t]
        for i in system.list_of_contact_points:
            for sigma in i.Sigma:
                for row in range(system.E[tau][i][sigma].shape[0]):
                    tau=list_of_environemnts[t]
                    a_x=LinExpr([(system.E[tau][i][sigma][row,k],x_TISHCOM[t,i,sigma,k]) for k in range(system.n)])
                    a_u=LinExpr([(system.E[tau][i][sigma][row,k+system.n],u_TISHCOM[t,i,sigma,k])  for k in range(system.m_u)])
                    a_lambda=LinExpr([(system.E[tau][i][sigma][row,k+system.n+system.m_u],lambda_TISHCOM[t,i,sigma,k]) for k in range(system.m_lambda)])
                    model.addConstr(a_x+a_u+a_lambda <= system.e[tau][i][sigma][row,0]*delta_TISHCOM[t,i,sigma])
                        
    # Equation b: Convexhull Dynamics
    model.addConstrs(x[t,j]==x_TISHCOM.sum(t,i,"*",j) for t in range(T) \
                                         for i in  system.list_of_contact_points for j in range(system.n))
    model.addConstrs(u[t,j]==u_TISHCOM.sum(t,i,"*",j) for t in range(T) \
                                         for i in  system.list_of_contact_points for j in range(system.m_u))
    model.addConstrs(u_lambda[t,j]==lambda_TISHCOM.sum(t,i,"*",j) for t in range(T) \
                                         for i in  system.list_of_contact_points for j in range(system.m_lambda))
    model.addConstrs(1==delta_TISHCOM.sum(t,i,"*") for t in range(T) \
                                         for i in  system.list_of_contact_points)
    
    # Equation c: Evolution
    for t in range(T):
        for row in range(system.n):
            tau=list_of_environemnts[t]
            a_x=LinExpr([(system.A[tau][row,k],x[t,k]) for k in range(system.n)])
            a_u=LinExpr([(system.B_u[tau][row,k],u[t,k]) for k in range(system.m_u)])
            a_lambda=LinExpr([(system.B_lambda[tau][row,k],u_lambda[t,k]) for k in range(system.m_lambda)])
            a_c=system.c[tau][row,0]
            model.addConstr(x[t+1,row]==a_x+a_u+a_lambda+a_c)
    
    
    # Goal Constraints
    for j in range(system.n):
        L=LinExpr()
        L.add(LinExpr([(goal.G[j,k],_p[goal,k]) for goal in list_of_goals for k in range(goal.G.shape[1])]))
        L.add(LinExpr([(goal.x[j,0],mu[goal]) for goal in list_of_goals]))
        model.addConstr(L==x[T,j])
    model.addConstr(mu.sum("*")==1)
    for goal in list_of_goals:
        for j in range(goal.G.shape[1]):
            model.addConstr(_p[goal,j]<=mu[goal])
            model.addConstr(-_p[goal,j]<=mu[goal])
    # Cost Engineering
    print "model built in",time.time()-t_start," seconds"
    # Optimize
    model.write("point_trajectory_time_stepping.lp")
    model.setParam("MIPfocus",1)
    model.setParam('TimeLimit', 6)
    if cost==2:
        J=QuadExpr(sum([u[t,j]*u[t,j] for j in optimize_controls_indices for t in range(T)]))
        model.setObjective(J,GRB.MINIMIZE)
        model.setParam('TimeLimit', time_limit)
        model.optimize()
    elif cost==1:
        u_abs=model.addVars(range(T),optimize_controls_indices,obj=1)
        model.update()
        model.addConstrs(u[t,j]<=u_abs[t,j] for t in range(T) for j in optimize_controls_indices)
        model.addConstrs(-u[t,j]<=u_abs[t,j] for t in range(T) for j in optimize_controls_indices)
        model.optimize()
    else:
        model.optimize()
    x_n={t:np.array([x[t,i].X for i in range(system.n)]) for t in range(T+1)}
    u_n={t:np.array([u[t,i].X for i in range(system.m_u)]) for t in range(T)}
    lambda_n={t:np.array([u_lambda[t,i].X for i in range(system.m_lambda)]) for t in range(T)}
    mode_n={}
    for t in range(T):
        mode_n[t]=[None]*len(system.list_of_contact_points)
        for tau in system.Eta:
            for i in system.list_of_contact_points:
                for sigma in i.Sigma:
                    if np.linalg.norm(delta_TISHCOM[t,i,sigma].X-1)<=10**-1:
                        mode_n[t][i.index]=sigma
        mode_n[t]=tuple(mode_n[t])
    print "*"*80
    return x_n,u_n,lambda_n,mode_n

    
def polytopic_trajectory_given_modes(x0,list_of_cells,goal,eps=0,order=1,scale=[]):
    """
    Description: 
        Polytopic Trajectory Optimization with the ordered list of polytopes given
        This is a convex program as mode sequence is already given
        list_of_cells: each cell has the following attributes: A,B,c, and polytope(H,h)
    """
    if len(scale)==0:
        scale=np.ones(x0.shape[0])
    model=Model("Fixed Mode Polytopic Trajectory")
    T=len(list_of_cells)
    n,m=list_of_cells[0].B.shape
    q=int(order*n)
    x=model.addVars(range(T+1),range(n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x")
    u=model.addVars(range(T),range(m),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u")
    G=model.addVars(range(T+1),range(n),range(q),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="G")
    theta=model.addVars(range(T),range(m),range(q),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="theta")
    model.update()
    
    print "inside function epsilon is",eps
    for j in range(n):
        model.addConstr(x[0,j]<=x0[j,0]+eps*scale[j])
        model.addConstr(x[0,j]>=x0[j,0]-eps*scale[j])

    for t in range(T):
        print "adding constraints of t",t
        cell=list_of_cells[t]
        A,B,c,_p=cell.A,cell.B,cell.c,cell.p
        for j in range(n):
            expr_x=LinExpr([(A[j,k],x[t,k]) for k in range(n)])
            expr_u=LinExpr([(B[j,k],u[t,k]) for k in range(m)])
            model.addConstr(x[t+1,j]==expr_x+expr_u+c[j,0])
        for i in range(n):
            for j in range(q):
                expr_x=LinExpr([(A[i,k],G[t,k,j]) for k in range(n)])
                expr_u=LinExpr([(B[i,k],theta[t,k,j]) for k in range(m)])
                model.addConstr(G[t+1,i,j]==expr_x+expr_u)
        x_t=np.array([x[t,j] for j in range(n)]).reshape(n,1)
        u_t=np.array([u[t,j] for j in range(m)]).reshape(m,1)
        G_t=np.array([G[t,i,j] for i in range(n) for j in range(q)]).reshape(n,q)
        theta_t=np.array([theta[t,i,j] for i in range(m) for j in range(q)]).reshape(m,q)
        GT=sp.linalg.block_diag(G_t,theta_t)
        xu=np.vstack((x_t,u_t))
        subset_LP(model,xu,GT,Ball(2*q),_p)
    x_T=np.array([x[T,j] for j in range(n)]).reshape(n,1)
    G_T=np.array([G[T,i,j] for i in range(n) for j in range(q)]).reshape(n,q)
    z=zonotope(x_T,G_T)
    subset_zonotopes(model,z,goal)
    # Cost function
    J=LinExpr([(1.0/scale[i]*(1/(t+1.5)),G[t,i,i]) for i in range(n) for t in range(T) if t%5==0])
    model.setObjective(J)
    model.write("polytopic_trajectory.lp")
    model.setParam('TimeLimit', 150)
    model.optimize()
    x_num,G_num,theta_num,u_num={},{},{},{}
    for t in range(T+1):
        x_num[t]=np.array([[x[t,j].X] for j in range(n)]).reshape(n,1)
        G_num[t]=np.array([[G[t,i,j].X] for i in range(n) for j in range(q)]).reshape(n,q)
    for t in range(T):
        theta_num[t]=np.array([[theta[t,i,j].X] for i in range(m) for j in range(q)]).reshape(m,q)
        u_num[t]=np.array([[u[t,i].X] for i in range(m) ]).reshape(m,1)
    return (x_num,u_num,G_num,theta_num)

def point_trajectory_given_modes_and_central_traj(x_traj,list_of_cells,goal,eps=0,scale=[]):
    """
    Description: 
        Point Trajectory Optimization with the ordered list of polytopes given
        This is a convex program as mode sequence is already given
        list_of_cells: each cell has the following attributes: A,B,c, and polytope(H,h)
    """
    model=Model("Fixed Mode Polytopic Trajectory")
    T=len(list_of_cells)
    n,m=list_of_cells[0].B.shape
    x=model.addVars(range(T+1),range(n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x")
    u=model.addVars(range(T),range(m),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u")
    model.update()
    if len(scale)==0:
        scale=np.ones(x_traj[0].shape[0])    
    print "inside function epsilon is",eps
    for j in range(n):
        model.addConstr(x[0,j]<=x_traj[0][j]+eps*scale[j])
        model.addConstr(x[0,j]>=x_traj[0][j]-eps*scale[j])

    for t in range(T):
        cell=list_of_cells[t]
        A,B,c,_p=cell.A,cell.B,cell.c,cell.p
        for j in range(n):
            expr_x=LinExpr([(A[j,k],x[t,k]) for k in range(n)])
            expr_u=LinExpr([(B[j,k],u[t,k]) for k in range(m)])
            model.addConstr(x[t+1,j]==expr_x+expr_u+c[j,0])
        x_t=np.array([x[t,j] for j in range(n)]).reshape(n,1)
        u_t=np.array([u[t,j] for j in range(m)]).reshape(m,1)
        xu=np.vstack((x_t,u_t))
        subset_LP(model,xu,np.zeros((n+m,1)),Ball(1),_p)


    x_T=np.array([x[T,j] for j in range(n)]).reshape(n,1)
    z=zonotope(x_T,np.zeros((n,1)))
    subset_generic(model,z,goal)
    # Cost function
    J=QuadExpr()
    for t in range(T):
        for i in range(n):
            J.add(x[t,i]*x[t,i]-x[t,i]*x_traj[t][i])
    model.setObjective(J)
    model.write("polytopic_trajectory.lp")
    model.setParam('TimeLimit', 150)
    model.optimize()
    x_num,u_num={},{}
    for t in range(T+1):
        x_num[t]=np.array([[x[t,j].X] for j in range(n)]).reshape(n,1)
    for t in range(T):
        u_num[t]=np.array([[u[t,i].X] for i in range(m) ]).reshape(m,1)
    return (x_num,u_num)



def disturbed_polytopic_trajectory_given_regions(x0,list_of_cells,goal,eps=0,order=1,scale=[]):
    """
    Description: 
        Polytopic Trajectory Optimization with the ordered list of polytopes given
        This is a convex program as mode sequence is already given
        list_of_cells: each cell has the following attributes: A,B,c,W and an AH-polytope
    """
    if len(scale)==0:
        scale=np.ones(x0.shape[0])
    model=Model("Fixed Mode Polytopic Trajectory")
    T=len(list_of_cells)
    n,m=list_of_cells[0].B.shape
    q=int(order*n)
    n_w=list_of_cells[0].w.G.shape[1]
    list_of_q=list(q+np.array(range(T))*n_w)
    print list_of_q
    x=model.addVars(range(T+1),range(n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x")
    u=model.addVars(range(T),range(m),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u")
    G,theta={},{}
    for t in range(T):
        _q=list_of_q[t]
        G[t]=model.addVars(range(n),range(_q),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="G_%d"%t)
        theta[t]=model.addVars(range(T),range(_q),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="theta_%s"%t)
    _q=list_of_q[T-1]+n_w
    G[T]=model.addVars(range(n),range(_q),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="G_%d"%T)
    model.update()
    print "inside function epsilon is",eps
    for j in range(n):
        model.addConstr(x[0,j]<=x0[j,0]+eps*scale[j])
        model.addConstr(x[0,j]>=x0[j,0]-eps*scale[j])

    for t in range(T):
        print "adding constraints of t",t
        cell=list_of_cells[t]
        A,B,w,p_x,p_u=cell.A,cell.B,cell.w,cell.p_x,cell.p_u
        _q=list_of_q[t]
        for j in range(n):
            expr_x=LinExpr([(A[j,k],x[t,k]) for k in range(n)])
            expr_u=LinExpr([(B[j,k],u[t,k]) for k in range(m)])
            model.addConstr(x[t+1,j]==expr_x+expr_u+w.x[j,0])
        for i in range(n):
            for j in range(_q):
                expr_x=LinExpr([(A[i,k],G[t][k,j]) for k in range(n)])
                expr_u=LinExpr([(B[i,k],theta[t][k,j]) for k in range(m)])
                model.addConstr(G[t+1][i,j]==expr_x+expr_u)
            for j in range(_q,_q+n_w):
                model.addConstr(G[t+1][i,j]==w.G[i,j-_q])
        x_t=np.array([x[t,j] for j in range(n)]).reshape(n,1)
        u_t=np.array([u[t,j] for j in range(m)]).reshape(m,1)
        G_t=np.array([G[t][i,j] for i in range(n) for j in range(_q)]).reshape(n,_q)
        theta_t=np.array([theta[t][i,j] for i in range(m) for j in range(_q)]).reshape(m,_q)
        X_t=zonotope(x_t,G_t)
        U_t=zonotope(u_t,theta_t)
        subset_generic(model,X_t,p_x)
        subset_generic(model,U_t,p_u)

    _q=list_of_q[T-1]+n_w
    x_T=np.array([x[T,j] for j in range(n)]).reshape(n,1)
    G_T=np.array([G[T][i,j] for i in range(n) for j in range(_q)]).reshape(n,_q)
    z=zonotope(x_T,G_T)
    subset_zonotopes(model,z,goal)
    # Cost function
    J=LinExpr([(1.0/scale[i],G[t][i,i]) for t in range(T+1) for i in range(n)])
    model.setObjective(J)
    model.write("polytopic_trajectory.lp")
    model.setParam('TimeLimit', 150)
    model.optimize()
    x_num,G_num,theta_num,u_num={},{},{},{}
    for t in range(T):
        x_num[t]=np.array([[x[t,j].X] for j in range(n)]).reshape(n,1)
        _q=list_of_q[t]
        G_num[t]=np.array([[G[t][i,j].X] for i in range(n) for j in range(_q)]).reshape(n,_q)
    _q=list_of_q[t]+n_w
    x_num[T]=np.array([[x[T,j].X] for j in range(n)]).reshape(n,1)
    G_num[T]=np.array([[G[T][i,j].X] for i in range(n) for j in range(_q)]).reshape(n,_q)
    for t in range(T):
        _q=list_of_q[t]
        theta_num[t]=np.array([[theta[t][i,j].X] for i in range(m) for j in range(_q)]).reshape(m,_q)
        u_num[t]=np.array([[u[t,i].X] for i in range(m) ]).reshape(m,1)
    return (x_num,u_num,G_num,theta_num)




def polytopic_trajectory(system,x0,list_of_goal_polytopes,T,eps=0.1,order=1):
    """
    Description: Polytopic Trajectory Optimization
    """
    model=Model("Point Trajectory Optimization")
    q=int(order*system.n)
    x=model.addVars(range(T+1),range(system.n),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x")
    u=model.addVars(range(T),range(system.m),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u")
    G=model.addVars(range(T+1),range(n),range(q),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="G")
    theta=model.addVars(range(T),range(m),range(q),lb=-GRB.INFINITY,ub=GRB.INFINITY,name="theta")
    ##
    x_PWA=model.addVars([(t,n,i,j) for t in range(T+1) for n in system.list_of_sum_indices \
                         for i in system.list_of_modes[n] for j in range(system.n)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="x_pwa")
    u_PWA=model.addVars([(t,n,i,j) for t in range(T) for n in system.list_of_sum_indices \
                         for i in system.list_of_modes[n] for j in range(system.m)],lb=-GRB.INFINITY,ub=GRB.INFINITY,name="u_pwa")
    G_PWA=model.addVars([(t,n,i,row,column) for t in range(T+1) for n in system.list_of_sum_indices \
                         for i in system.list_of_modes[n] for row in range(system.n) for column in range(q)],\
                        lb=-GRB.INFINITY,ub=GRB.INFINITY,name="G_pwa")
    theta_PWA=model.addVars([(t,n,i,row,column) for t in range(T+1) for n in system.list_of_sum_indices \
                         for i in system.list_of_modes[n] for row in range(system.m) for column in range(q)],\
                        lb=-GRB.INFINITY,ub=GRB.INFINITY,name="theta_pwa")
    delta_PWA=model.addVars([(t,n,i) for t in range(T) for n in system.list_of_sum_indices \
                             for i in system.list_of_modes[n]],vtype=GRB.BINARY,name="delta_pwa")
    model.update()
    for j in range(n):
        model.addConstr(x[0,j]<=x0[j,0]+eps*system.scale[j])
        model.addConstr(x[0,j]>=x0[j,0]-eps*system.scale[j])
    
    # Convexhull Dynamics and Constraints
    model.addConstrs(x[t,j]==x_PWA.sum(t,n,"*",j) for t in range(T+1) for j in range(system.n)\
                     for n in system.list_of_sum_indices)
    model.addConstrs(u[t,j]==u_PWA.sum(t,n,"*",j) for t in range(T) for j in range(system.m)\
                     for n in system.list_of_sum_indices)   
    model.addConstrs(G[t,row,column]==G_PWA.sum(t,n,"*",row,column) for t in range(T) for row in range(system.n)\
                     for column in range(q) for n in system.list_of_sum_indices) 
    model.addConstrs(G[t,row,column]==G_PWA.sum(t,n,"*",row,column) for t in range(T) for row in range(system.n)\
                     for column in range(q) for n in system.list_of_sum_indices) 
    raise NotImplementedError    



def Ball(n):
    H=np.vstack((np.eye(n),-np.eye(n)))
    h=np.ones((2*n,1))
    return polytope(H,h)


def add_initial_condition(system,model,x,x0,eps):
    """
    eps=system
    """
    if eps==None:
        print "no epsilon is given"
        model.addConstrs(x[0,i]==x0[i,0] for i in range(system.n))
    else:
        epsilon=model.addVars(range(system.n),lb=-eps,ub=eps)
        model.update()
        model.addConstrs(x[0,i]==x0[i,0]+epsilon[i]*system.scale[i] for i in range(system.n))


def tupledict(A):
    """
    Converts matrix to dict
    """
    if len(A.shape)==1:
        return {i:A[i] for i in range(A.shape[0])}
    elif len(A.shape)==2:
        return {(i,j):A[i,j] for i in range(A.shape[0]) for j in range(A.shape[1])}
    else:
        raise NotImplementedError
        
def valuation_t(x):
    """
    Description: given a set of Gurobi variables, output a similar object with values
    Input:
        x: dictionary or a vector, each val an numpy array, each entry a Gurobi variable
        output: x_n: dictionary with the same key as, each val an numpy array, each entry a float 
    """
    if type(x)==type(dict()):
        for key,val in x.items():
            x_n[key]=ones(val.shape)
            (n_r,n_c)=val.shape
            for row in range(n_r):
                for column in range(n_c):
                    x_n[key][row,column]=x[key][row,column].X   
        return x_n
    else:
        raise("x is neither a dictionary or a numpy array")
        
def block_diag(*arrs):
    """
    Create a block diagonal matrix from provided arrays.
    Given the inputs `A`, `B` and `C`, the output will have these
    arrays arranged on the diagonal::
        [[A, 0, 0],
         [0, B, 0],
         [0, 0, C]]
    Parameters
    ----------
    A, B, C, ... : array_like, up to 2-D
        Input arrays.  A 1-D array or array_like sequence of length `n`is
        treated as a 2-D array with shape ``(1,n)``.
    Returns
    -------
    D : ndarray
        Array with `A`, `B`, `C`, ... on the diagonal.  `D` has the
        same dtype as `A`.
    Notes
    -----
    If all the input arrays are square, the output is known as a
    block diagonal matrix.
    Examples
    --------
    >>> from scipy.linalg import block_diag
    >>> A = [[1, 0],
    ...      [0, 1]]
    >>> B = [[3, 4, 5],
    ...      [6, 7, 8]]
    >>> C = [[7]]
    >>> block_diag(A, B, C)
    [[1 0 0 0 0 0]
     [0 1 0 0 0 0]
     [0 0 3 4 5 0]
     [0 0 6 7 8 0]
     [0 0 0 0 0 7]]
    >>> block_diag(1.0, [2, 3], [[4, 5], [6, 7]])
    array([[ 1.,  0.,  0.,  0.,  0.],
           [ 0.,  2.,  3.,  0.,  0.],
           [ 0.,  0.,  0.,  4.,  5.],
           [ 0.,  0.,  0.,  6.,  7.]])
    """
    if arrs == ():
        arrs = ([],)
    arrs = [np.atleast_2d(a) for a in arrs]

    bad_args = [k for k in range(len(arrs)) if arrs[k].ndim > 2]
    if bad_args:
        raise ValueError("arguments in the following positions have dimension "
                            "greater than 2: %s" % bad_args)

    shapes = np.array([a.shape for a in arrs])
    out = np.zeros(np.sum(shapes, axis=0), dtype=arrs[0].dtype)

    r, c = 0, 0
    for i, (rr, cc) in enumerate(shapes):
        out[r:r + rr, c:c + cc] = arrs[i]
        r += rr
        c += cc
    return out