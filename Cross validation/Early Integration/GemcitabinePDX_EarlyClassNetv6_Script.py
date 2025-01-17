import torch 
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd
import math
import sklearn.preprocessing as sk
import seaborn as sns
from sklearn import metrics
from sklearn.feature_selection import VarianceThreshold
from sklearn.model_selection import train_test_split
from utils import AllTripletSelector,HardestNegativeTripletSelector, RandomNegativeTripletSelector, SemihardNegativeTripletSelector # Strategies for selecting triplets within a minibatch
from metrics import AverageNonzeroTripletsMetric
from torch.utils.data.sampler import WeightedRandomSampler
from sklearn.metrics import roc_auc_score
from sklearn.metrics import average_precision_score
import random
from sklearn.model_selection import StratifiedKFold

save_results_to = '/home/hnoghabi/EarlyClassNetv6/Gemcitabine/'
torch.manual_seed(42)

max_iter = 50

GDSCE = pd.read_csv("GDSC_exprs.Gemcitabine.eb_with.PDX_exprs.Gemcitabine.tsv", 
                    sep = "\t", index_col=0, decimal = ",")
GDSCE = pd.DataFrame.transpose(GDSCE)

GDSCR = pd.read_csv("GDSC_response.Gemcitabine.tsv", 
                    sep = "\t", index_col=0, decimal = ",")

PDXE = pd.read_csv("PDX_exprs.Gemcitabine.eb_with.GDSC_exprs.Gemcitabine.tsv", 
                   sep = "\t", index_col=0, decimal = ",")
PDXE = pd.DataFrame.transpose(PDXE)

PDXM = pd.read_csv("PDX_mutations.Gemcitabine.tsv", 
                   sep = "\t", index_col=0, decimal = ",")
PDXM = pd.DataFrame.transpose(PDXM)

PDXC = pd.read_csv("PDX_CNA.Gemcitabine.tsv", 
                   sep = "\t", index_col=0, decimal = ",")
PDXC.drop_duplicates(keep='last')
PDXC = pd.DataFrame.transpose(PDXC)
PDXC = PDXC.loc[:,~PDXC.columns.duplicated()]

GDSCM = pd.read_csv("GDSC_mutations.Gemcitabine.tsv", 
                    sep = "\t", index_col=0, decimal = ",")
GDSCM = pd.DataFrame.transpose(GDSCM)


GDSCC = pd.read_csv("GDSC_CNA.Gemcitabine.tsv", 
                    sep = "\t", index_col=0, decimal = ",")
GDSCC.drop_duplicates(keep='last')
GDSCC = pd.DataFrame.transpose(GDSCC)

selector = VarianceThreshold(0.05)
selector.fit_transform(GDSCE)
GDSCE = GDSCE[GDSCE.columns[selector.get_support(indices=True)]]

PDXC = PDXC.fillna(0)
PDXC[PDXC != 0.0] = 1
PDXM = PDXM.fillna(0)
PDXM[PDXM != 0.0] = 1
GDSCM = GDSCM.fillna(0)
GDSCM[GDSCM != 0.0] = 1
GDSCC = GDSCC.fillna(0)
GDSCC[GDSCC != 0.0] = 1

ls = GDSCE.columns.intersection(GDSCM.columns)
ls = ls.intersection(GDSCC.columns)
ls = ls.intersection(PDXE.columns)
ls = ls.intersection(PDXM.columns)
ls = ls.intersection(PDXC.columns)
ls2 = GDSCE.index.intersection(GDSCM.index)
ls2 = ls2.intersection(GDSCC.index)
ls3 = PDXE.index.intersection(PDXM.index)
ls3 = ls3.intersection(PDXC.index)
ls = pd.unique(ls)

PDXE = PDXE.loc[ls3,ls]
PDXM = PDXM.loc[ls3,ls]
PDXC = PDXC.loc[ls3,ls]
GDSCE = GDSCE.loc[ls2,ls]
GDSCM = GDSCM.loc[ls2,ls]
GDSCC = GDSCC.loc[ls2,ls]

GDSCR.loc[GDSCR.iloc[:,0] == 'R'] = 0
GDSCR.loc[GDSCR.iloc[:,0] == 'S'] = 1
GDSCR.columns = ['targets']
GDSCR = GDSCR.loc[ls2,:]

PDXR = pd.read_csv("PDX_response.Gemcitabine.tsv", 
                       sep = "\t", index_col=0, decimal = ",")
PDXR.loc[PDXR.iloc[:,0] == 'R'] = 0
PDXR.loc[PDXR.iloc[:,0] == 'S'] = 1

Y = GDSCR['targets'].values
#y_test = TCGAR['response'].values

ls_mb_size = [32, 62]
ls_lr = [0.5, 0.1, 0.05, 0.01, 0.001, 0.005, 0.0005, 0.0001,0.00005, 0.00001]
ls_epoch = [20, 50, 10, 15]
ls_rate = [0.2, 0.3, 0.4, 0.5]
ls_wd = [0.1, 0.01, 0.001, 0.0001]
skf = StratifiedKFold(n_splits=7, random_state=42)
    
for iters in range(max_iter):
    k = 0
    mbs = random.choice(ls_mb_size)
    h_dim = 256
    z_dim = 128
    Z_in = z_dim
    lrCL = random.choice(ls_lr)
    epch = random.choice(ls_epoch)
    rate = random.choice(ls_rate)
    wd = random.choice(ls_wd) 

    for train_index, test_index in skf.split(GDSCE.values, Y):
        k = k + 1
        X_trainE = GDSCE.values[train_index,:]
        X_testE =  GDSCE.values[test_index,:]
        X_trainM = GDSCM.values[train_index,:]
        X_testM = GDSCM.values[test_index,:]
        X_trainC = GDSCC.values[train_index,:]
        X_testC = GDSCM.values[test_index,:]
        y_trainE = Y[train_index]
        y_testE = Y[test_index]
        
        scalerGDSC = sk.StandardScaler()
        scalerGDSC.fit(X_trainE)
        X_trainE = scalerGDSC.transform(X_trainE)
        X_testE = scalerGDSC.transform(X_testE)

        X_trainM = np.nan_to_num(X_trainM)
        X_trainC = np.nan_to_num(X_trainC)
        X_testM = np.nan_to_num(X_testM)
        X_testC = np.nan_to_num(X_testC)
        
        TX_testE = torch.FloatTensor(X_testE)
        TX_testM = torch.FloatTensor(X_testM)
        TX_testC = torch.FloatTensor(X_testC)
        ty_testE = torch.FloatTensor(y_testE.astype(int))
        
        #Train
        class_sample_count = np.array([len(np.where(y_trainE==t)[0]) for t in np.unique(y_trainE)])
        weight = 1. / class_sample_count
        samples_weight = np.array([weight[t] for t in y_trainE])

        samples_weight = torch.from_numpy(samples_weight)
        sampler = WeightedRandomSampler(samples_weight.type('torch.DoubleTensor'), len(samples_weight), replacement=True)

        mb_size = mbs

        trainDataset = torch.utils.data.TensorDataset(torch.FloatTensor(X_trainE), torch.FloatTensor(X_trainM), 
                                                      torch.FloatTensor(X_trainC), torch.FloatTensor(y_trainE.astype(int)))

        trainLoader = torch.utils.data.DataLoader(dataset = trainDataset, batch_size=mb_size, shuffle=False, num_workers=1, sampler = sampler)

        n_sampE, IE_dim = X_trainE.shape
        n_sampM, IM_dim = X_trainM.shape
        n_sampC, IC_dim = X_trainC.shape
    
        epoch = epch

        costtr = []
        auctr = []
        costts = []
        aucts = []

        class AE(nn.Module):
            def __init__(self):
                super(AE, self).__init__()
                self.EnE = torch.nn.Sequential(
                    nn.Linear(input_dim, h_dim),
                    nn.ReLU(),
                    nn.BatchNorm1d(h_dim),
                    nn.Dropout(),
                    nn.Linear(h_dim, z_dim),
                    nn.ReLU(),
                    nn.BatchNorm1d(z_dim))
                self.DeE = torch.nn.Sequential(
                    nn.Linear(z_dim, h_dim),
                    nn.ReLU(),
                    nn.BatchNorm1d(h_dim),
                    nn.Dropout(),
                    nn.Linear(h_dim, input_dim),
                    nn.ReLU(),
                    nn.BatchNorm1d(input_dim))      
            def forward(self, x):
                output = self.EnE(x)
                Xhat = self.DeE(output)
                return Xhat, output           

        torch.cuda.manual_seed_all(42)

        AutoencoderE = torch.load('EarlyGemPDXv5.pt')
        
        class Classifier(nn.Module):
            def __init__(self):
                super(Classifier, self).__init__()
                self.FC = torch.nn.Sequential(
                    nn.Linear(Z_in, 1),
                    nn.Dropout(rate),
                    nn.Sigmoid())
            def forward(self, x):
                return self.FC(x)        
        
        Clas = Classifier()
        SolverClass = optim.Adagrad(Clas.parameters(), lr=lrCL, weight_decay = wd)
        C_loss = torch.nn.BCELoss()

        for it in range(epoch):

            epoch_cost4 = 0
            epoch_cost3 = []
            num_minibatches = int(n_sampE / mb_size) 

            for i, (dataE, dataM, dataC, target) in enumerate(trainLoader):
                flag = 0
                AutoencoderE.eval()
                Clas.train()
                
                if torch.mean(target)!=0. and torch.mean(target)!=1.:                      
                    Dat_train = torch.cat((dataE, dataM, dataC), 1)
                    Dat_hat, ZX = AutoencoderE(Dat_train)

                    Pred = Clas(ZX)

                    loss = C_loss(Pred,target.view(-1,1))     

                    y_true = target.view(-1,1)
                    y_pred = Pred
                    AUC = roc_auc_score(y_true.detach().numpy(),y_pred.detach().numpy()) 

                    SolverClass.zero_grad()

                    loss.backward()

                    SolverClass.step()

                    epoch_cost4 = epoch_cost4 + (loss / num_minibatches)
                    epoch_cost3.append(AUC)
                    flag = 1

            if flag == 1:
                costtr.append(torch.mean(epoch_cost4))
                auctr.append(np.mean(epoch_cost3))
                print('Iter-{}; Total loss: {:.4}'.format(it, loss))

            with torch.no_grad():

                AutoencoderE.eval()
                Clas.eval()

                Dat_test = torch.cat((TX_testE, TX_testM, TX_testC), 1)
                Dat_hatt, ZT = AutoencoderE(Dat_test)
                
                PredT = Clas(ZT)

                lossT = C_loss(PredT,ty_testE.view(-1,1))

                y_truet = ty_testE.view(-1,1)
                y_predt = PredT
                AUCt = roc_auc_score(y_truet.detach().numpy(),y_predt.detach().numpy())        

                costts.append(lossT)
                aucts.append(AUCt)

        plt.plot(np.squeeze(costtr), '-r',np.squeeze(costts), '-b')
        plt.ylabel('Total cost')
        plt.xlabel('iterations (per tens)')

        title = 'Cost Gemcitabine iter = {}, fold = {}, mb_size = {},  z_dim = {}, epoch = {}, rate = {}, wd = {}, lrCL = {}'.\
                      format(iters, k, mbs, z_dim, epch, rate, wd, lrCL)  

        plt.suptitle(title)
        plt.savefig(save_results_to + title + '.png', dpi = 150)
        plt.close()

        plt.plot(np.squeeze(auctr), '-r',np.squeeze(aucts), '-b')
        plt.ylabel('AUC')
        plt.xlabel('iterations (per tens)')

        title = 'AUC Gemcitabine iter = {}, fold = {}, mb_size = {},  z_dim = {}, epoch = {}, rate = {}, wd = {}, lrCL = {}'.\
                      format(iters, k, mbs, z_dim, epch, rate, wd, lrCL)        

        plt.suptitle(title)
        plt.savefig(save_results_to + title + '.png', dpi = 150)
        plt.close()
