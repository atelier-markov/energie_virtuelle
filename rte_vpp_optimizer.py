# rte_vpp_optimizer.py
# 
# Variables
#   x_charge[t]: energy charged at timestep t, >=0 kWh
#   x_discharge[t]: energy discharged at timestep t,>=0 kWh
#   SoC[t]: battery state of charge at timestep t, 0.2<=SoC[t]<=0.9
#   SoC[t] = SoC[0] + sum_{k=0}^{t-1} (efficiency * x_charge[k] - x_discharge[k]/efficiency)
#
# objective function, profit= energy_sold - energy_charged/eta
# Net_Profit = sum(price[t] * (x_discharge[t] - x_charge[t])) / 1000   #convert kWh to MWh
# 
# maximize Net_Profit (i.e., minimize -Net_Profit)
# linprog minimizes c^T * x, so c=+price for charge, -price for discharge

# Copyright (c) 2026 Rashid Vladimir Williams-Garcia, Atelier Markov
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import numpy as np
from scipy.optimize import linprog
import pandas as pd

def optimize_vpp(df, energy_capacity, power_max, efficiency, soc_initial, soc_min, soc_max):
    prices = df['price']
    T = len(prices)  #number of timesteps (hours)

    c = np.zeros(2*T)
    c[0:T] = prices  #constants corresponding to x_charge
    c[T:2*T] = -prices #... x_discharge

    #Constraints: A_ub * x <= b_ub and A_eq * x == b_eq
    A_ub = []
    b_ub = []

    #1) Define charge/discharge limits per timestep
    for t in range(T):
        #charge rate <= power_max
        row_charge = np.zeros(2*T)
        row_charge[t] = 1
        A_ub.append(row_charge)
        b_ub.append(power_max)

        #discharge rate <= power_max
        row_discharge = np.zeros(2*T)
        row_discharge[T+t] = 1
        A_ub.append(row_discharge)
        b_ub.append(power_max)

    #2) SoC bounds
    for t in range(1,T+1): #t from 1 to T
        row_min = np.zeros(2*T)
        row_max = np.zeros(2*T)

        for k in range(t):
            row_min[k] = -efficiency
            row_min[T+k] = 1/efficiency

            row_max[k] = efficiency
            row_max[T+k] = -1/efficiency

        #soc[t] >= soc_min * energy_capacity or -soc[t] <= -soc_min * energy_capacity
        A_ub.append(row_min)
        b_ub.append(-soc_min * energy_capacity + soc_initial)

        A_ub.append(row_max)
        b_ub.append(soc_max * energy_capacity - soc_initial)

    #3) Final SoC constraints (at the end, should have initial SoC for VPP continuity?)
    row_final = np.zeros(2*T)

    for t in range(T):
        row_final[t] = efficiency
        row_final[T+t] = -1/efficiency

    A_ub = np.array(A_ub)
    b_ub = np.array(b_ub)

    #Bounds: all variables >= 0
    bounds = [(0, None)] * (2*T)

    #Optimize using linprog
    result = linprog(c, A_ub, b_ub, None, None, bounds, method='highs')

    if result.success:
        x_charge = result.x[0:T]
        x_discharge = result.x[T:2*T]
        profit = -result.fun / 1000   #linprog minimizes negative profit, convert to euros
        
        soc = np.zeros(T)

        for t in range(T):
            if t==0:
                soc[t] = soc_initial + efficiency * x_charge[t] - (1.0/efficiency) * x_discharge[t]
            else:
                soc[t] = soc[t-1] + efficiency * x_charge[t] - (1.0/efficiency) * x_discharge[t]

        df['x_charge'] = x_charge
        df['x_discharge'] = x_discharge
        df['profit'] = prices * (x_discharge - x_charge) / 1000
        df['soc'] = soc

    else:
        print("Linear optimization failed")
        print(result.message)
    
    return df
