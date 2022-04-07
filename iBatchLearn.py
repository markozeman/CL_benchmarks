import os
import sys
import argparse
import torch
import time
import numpy as np
from random import shuffle
from collections import OrderedDict

from torch import Tensor
from torch.utils.data import TensorDataset

import dataloaders.base
from dataloaders.datasetGen import SplitGen, PermutedGen
import agents
from agents.default import plot_multiple_histograms


def get_data(s):
    """
    Get data for string s abbreviation.

    :param s: string of dataset abbreviation name
    :return: X, y, mask
    """
    if s == 'HS':
        X = torch.load('Word2Vec_embeddings/X_hate_speech.pt').float()
        y = torch.load('Word2Vec_embeddings/y_hate_speech.pt')
        mask = torch.load('Word2Vec_embeddings/mask_hate_speech.pt').float()
    elif s == 'SA':
        X = torch.load('Word2Vec_embeddings/X_IMDB_sentiment_analysis.pt').float()
        y = torch.load('Word2Vec_embeddings/y_IMDB_sentiment_analysis.pt')
        mask = torch.load('Word2Vec_embeddings/mask_IMDB_sentiment_analysis.pt').float()
    elif s == 'S':
        X = torch.load('Word2Vec_embeddings/X_sms_spam.pt').float()
        y = torch.load('Word2Vec_embeddings/y_sms_spam.pt')
        mask = torch.load('Word2Vec_embeddings/mask_sms_spam.pt').float()
    elif s == 'SA_2':
        X = torch.load('Word2Vec_embeddings/X_sentiment_analysis_2.pt').float()
        y = torch.load('Word2Vec_embeddings/y_sentiment_analysis_2.pt')
        mask = torch.load('Word2Vec_embeddings/mask_sentiment_analysis_2.pt').float()
    elif s == 'C':
        X = torch.load('Word2Vec_embeddings/X_clickbait.pt').float()
        y = torch.load('Word2Vec_embeddings/y_clickbait.pt')
        mask = torch.load('Word2Vec_embeddings/mask_clickbait.pt').float()
    elif s == 'HD':
        X = torch.load('Word2Vec_embeddings/X_humor_detection.pt').float()
        y = torch.load('Word2Vec_embeddings/y_humor_detection.pt')
        mask = torch.load('Word2Vec_embeddings/mask_humor_detection.pt').float()

    return X, y, mask


def run(args, do_early_stopping, stopping_criteria, task_names):
    if not os.path.exists('outputs'):
        os.mkdir('outputs')

    # todo
    '''
    # Prepare dataloaders
    train_dataset, val_dataset = dataloaders.base.__dict__[args.dataset](args.dataroot, args.train_aug)
    if args.n_permutation>0:
        train_dataset_splits, val_dataset_splits, task_output_space = PermutedGen(train_dataset, val_dataset,
                                                                             args.n_permutation,
                                                                             remap_class=not args.no_class_remap)
    else:
        train_dataset_splits, val_dataset_splits, task_output_space = SplitGen(train_dataset, val_dataset,
                                                                          first_split_sz=args.first_split_size,
                                                                          other_split_sz=args.other_split_size,
                                                                          rand_split=args.rand_split,
                                                                          remap_class=not args.no_class_remap)
    '''

    # task_names = ['HS', 'SA', 'S', 'SA_2', 'C', 'HD']
    task_output_space = {name: 2 for name in task_names}
    test_all_tasks = []

    # Prepare the Agent (model)
    agent_config = {'lr': args.lr, 'momentum': args.momentum, 'weight_decay': args.weight_decay,'schedule': args.schedule,
                    'model_type':args.model_type, 'model_name': args.model_name, 'model_weights':args.model_weights,
                    'out_dim':{'All':args.force_out_dim} if args.force_out_dim>0 else task_output_space,
                    'optimizer':args.optimizer,
                    'print_freq':args.print_freq, 'gpuid': args.gpuid,
                    'reg_coef':args.reg_coef}
    agent = agents.__dict__[args.agent_type].__dict__[args.agent_name](agent_config)
    print(agent.model)
    print('#parameter of model:',agent.count_parameter())

    # Decide split ordering
    # task_names = sorted(list(task_output_space.keys()), key=int)    # todo
    # print('Task order:',task_names)
    # if args.rand_split_order:
    #     shuffle(task_names)
    #     print('Shuffled task order:', task_names)

    acc_table = OrderedDict()
    auroc_table = OrderedDict()
    auprc_table = OrderedDict()
    epochs = []

    if args.offline_training:  # Non-incremental learning / offline_training / measure the upper-bound performance
        pass
        # task_names = ['All']
        # train_dataset_all = torch.utils.data.ConcatDataset(train_dataset_splits.values())
        # val_dataset_all = torch.utils.data.ConcatDataset(val_dataset_splits.values())
        # train_loader = torch.utils.data.DataLoader(train_dataset_all,
        #                                            batch_size=args.batch_size, shuffle=True, num_workers=args.workers)
        # val_loader = torch.utils.data.DataLoader(val_dataset_all,
        #                                          batch_size=args.batch_size, shuffle=False, num_workers=args.workers)
        #
        # agent.learn_batch(train_loader, val_loader)
        #
        # acc_table['All'] = {}
        # acc_table['All']['All'] = agent.validation(val_loader)

    else:  # Incremental learning
        # Feed data to agent and evaluate agent's performance
        for i in range(len(task_names)):
            train_name = task_names[i]
            print('======================',train_name,'=======================')

            # prepare data
            X, y, mask = get_data(train_name)

            # split data into train, validation and test set
            y = torch.max(y, 1)[1]  # change one-hot-encoded vectors to numbers
            permutation = torch.randperm(X.size()[0])
            X = X[permutation]
            y = y[permutation]
            mask = mask[permutation]
            index_val = round(0.8 * len(permutation))
            index_test = round(0.9 * len(permutation))

            # X_train, y_train, mask_train = X[:index_val, :, :].to("cuda:0"), y[:index_val].to("cuda:0"), mask[:index_val,:].to("cuda:0")  # train data to GPU
            X_train, y_train, mask_train = X[:index_val, :, :], y[:index_val], mask[:index_val,:]
            X_val, y_val, mask_val = X[index_val:index_test, :, :], y[index_val:index_test], mask[index_val:index_test,:]
            X_test, y_test, mask_test = X[index_test:, :, :], y[index_test:], mask[index_test:, :]

            # tasks4compatibility = np.array(tuple([str(i + 1)] * args.batch_size))
            train_dataset = TensorDataset(X_train, y_train, mask_train)     # mask not used
            val_dataset = TensorDataset(X_val, y_val, mask_val)
            test_dataset = TensorDataset(X_test, y_test, mask_test)

            train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=args.batch_size)
            val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=args.batch_size)
            test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=args.batch_size)

            # save test data for every task
            test_all_tasks.append(test_loader)

            # todo
            '''
            train_loader = torch.utils.data.DataLoader(train_dataset_splits[train_name],
                                                        batch_size=args.batch_size, shuffle=True, num_workers=args.workers)
            val_loader = torch.utils.data.DataLoader(val_dataset_splits[train_name],
                                                      batch_size=args.batch_size, shuffle=False, num_workers=args.workers)
            '''

            if args.incremental_class:
                agent.add_valid_output_dim(task_output_space[train_name])

            # Learn
            epochs_trained = agent.learn_batch(train_loader, val_loader, do_early_stopping, stopping_criteria)
            epochs.append(epochs_trained)

            # Evaluate
            acc_table[train_name] = OrderedDict()
            auroc_table[train_name] = OrderedDict()
            auprc_table[train_name] = OrderedDict()
            for j in range(i+1):
                val_name = task_names[j]
                print('Test split name:', val_name)

                # todo
                # print('validation split name:', val_name)
                # val_data = val_dataset_splits[val_name] if not args.eval_on_train_set else train_dataset_splits[val_name]
                # val_loader = torch.utils.data.DataLoader(val_data,
                #                                          batch_size=args.batch_size, shuffle=False,
                #                                          num_workers=args.workers)
                # acc_table[val_name][train_name] = agent.validation(val_loader)

                acc, auroc, auprc = agent.validation(test_all_tasks[j], is_test=True)
                print('acc, auroc, auprc:', acc, auroc, auprc)

                acc_table[val_name][train_name] = acc
                auroc_table[val_name][train_name] = auroc
                auprc_table[val_name][train_name] = auprc

    return acc_table, auroc_table, auprc_table, task_names, epochs


def get_args(argv):
    # This function prepares the variables shared across demo.py
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpuid', nargs="+", type=int, default=[0],
                        help="The list of gpuid, ex:--gpuid 3 1. Negative value means cpu-only")
    parser.add_argument('--model_type', type=str, default='mlp', help="The type (mlp|lenet|vgg|resnet) of backbone network")
    parser.add_argument('--model_name', type=str, default='MLP', help="The name of actual model for the backbone")
    parser.add_argument('--force_out_dim', type=int, default=2, help="Set 0 to let the task decide the required output dimension")
    parser.add_argument('--agent_type', type=str, default='default', help="The type (filename) of agent")
    parser.add_argument('--agent_name', type=str, default='NormalNN', help="The class name of agent")
    parser.add_argument('--optimizer', type=str, default='SGD', help="SGD|Adam|RMSprop|amsgrad|Adadelta|Adagrad|Adamax ...")
    parser.add_argument('--dataroot', type=str, default='data', help="The root folder of dataset or downloaded data")
    parser.add_argument('--dataset', type=str, default='MNIST', help="MNIST(default)|CIFAR10|CIFAR100")
    parser.add_argument('--n_permutation', type=int, default=10, help="Enable permuted tests when >0")
    parser.add_argument('--first_split_size', type=int, default=2)
    parser.add_argument('--other_split_size', type=int, default=2)
    parser.add_argument('--no_class_remap', dest='no_class_remap', default=True, action='store_true',
                        help="Avoid the dataset with a subset of classes doing the remapping. Ex: [2,5,6 ...] -> [0,1,2 ...]")
    parser.add_argument('--train_aug', dest='train_aug', default=False, action='store_true',
                        help="Allow data augmentation during training")
    parser.add_argument('--rand_split', dest='rand_split', default=False, action='store_true',
                        help="Randomize the classes in splits")
    parser.add_argument('--rand_split_order', dest='rand_split_order', default=False, action='store_true',
                        help="Randomize the order of splits")
    parser.add_argument('--workers', type=int, default=3, help="#Thread for dataloader")
    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--lr', type=float, default=0.001, help="Learning rate")
    parser.add_argument('--momentum', type=float, default=0)
    parser.add_argument('--weight_decay', type=float, default=0)
    parser.add_argument('--schedule', nargs="+", type=int, default=[2],
                        help="The list of epoch numbers to reduce learning rate by factor of 0.1. Last number is the end epoch")
    parser.add_argument('--print_freq', type=float, default=100, help="Print the log at every x iteration")
    parser.add_argument('--model_weights', type=str, default=None,
                        help="The path to the file for the model weights (*.pth).")
    parser.add_argument('--reg_coef', nargs="+", type=float, default=[0.], help="The coefficient for regularization. Larger means less plasilicity. Give a list for hyperparameter search.")
    parser.add_argument('--eval_on_train_set', dest='eval_on_train_set', default=False, action='store_true',
                        help="Force the evaluation on train set")
    parser.add_argument('--offline_training', dest='offline_training', default=False, action='store_true',
                        help="Non-incremental learning by make all data available in one batch. For measuring the upperbound performance.")
    parser.add_argument('--repeat', type=int, default=1, help="Repeat the experiment N times")
    parser.add_argument('--incremental_class', dest='incremental_class', default=False, action='store_true',
                        help="The number of output node in the single-headed model increases along with new categories.")
    args = parser.parse_args(argv)
    return args


if __name__ == '__main__':
    args = get_args(sys.argv[1:])
    reg_coef_list = args.reg_coef
    avg_final_acc = {}
    do_early_stopping = True
    stopping_criteria = 'auroc'  # possibilities: 'acc', 'auroc', 'auprc'
    args.repeat = 2   # number of runs
    args.agent_name = 'MAS'   # continual learning method; options: ['EWC_mnist', 'EWC_online_mnist', 'SI', 'MAS', 'GEM_x']

    args.force_out_dim = 2  # number of output neurons / number of classes
    args.model_name = 'myTransformer'  # to use Transformer model
    args.agent_type = 'regularization' if args.agent_name == 'MAS' or args.agent_name == 'SI' else 'customization'
    args.optimizer = 'SGD' if args.agent_name.startswith('GEM') else 'Adam'
    best_reg_coefs = {      # based on coefficient search
        'EWC_mnist': 5000,  # _mnist does not mean we run it on MNIST (used for backward compatibility)
        'EWC_online_mnist': 5000,   # _mnist does not mean we run it on MNIST (used for backward compatibility)
        'SI': 2,
        'MAS': 50,
        'GEM_510': 0.005,
        'GEM_60': 0.005,
        'GEM_30': 0.005,
        'GEM_15': 0.005,
        'GEM_12': 0.005
    }
    reg_coef_list = [best_reg_coefs[args.agent_name]]

    # The for loops over hyper-paramerters or repeats
    for reg_coef in reg_coef_list:
        args.reg_coef = reg_coef
        avg_final_acc[reg_coef] = np.zeros(args.repeat)

        avg_acc_history_all_repeats = []
        avg_auroc_history_all_repeats = []
        avg_auprc_history_all_repeats = []
        times_per_run = []
        epochs_per_run = []

        runs_task_names = [['HS', 'SA', 'S', 'SA_2', 'C', 'HD'],
                           ['C', 'HD', 'SA', 'HS', 'SA_2', 'S'],
                           ['SA', 'S', 'HS', 'SA_2', 'HD', 'C'],
                           ['HD', 'SA_2', 'SA', 'C', 'S', 'HS'],
                           ['SA', 'HS', 'C', 'SA_2', 'HD', 'S']]

        for r in range(args.repeat):
            print('- - Run %d - -' % (r + 1))

            start_time = time.time()

            # Run the experiment
            acc_table, auroc_table, auprc_table, task_names, epochs = run(args, do_early_stopping, stopping_criteria, runs_task_names[r])
            print('Accuracy dict:', acc_table)
            print('AUROC dict:', auroc_table)
            print('AUPRC dict:', auprc_table)

            epochs_per_run.append(epochs)

            # Calculate average performance across tasks
            # Customize this part for a different performance metric
            avg_acc_history = [0] * len(task_names)
            avg_auroc_history = [0] * len(task_names)
            avg_auprc_history = [0] * len(task_names)
            for i in range(len(task_names)):
                train_name = task_names[i]
                cls_acc_sum = 0
                cls_auroc_sum = 0
                cls_auprc_sum = 0
                for j in range(i + 1):
                    val_name = task_names[j]
                    cls_acc_sum += acc_table[val_name][train_name]
                    cls_auroc_sum += auroc_table[val_name][train_name]
                    cls_auprc_sum += auprc_table[val_name][train_name]

                avg_acc_history[i] = cls_acc_sum / (i + 1)
                avg_auroc_history[i] = cls_auroc_sum / (i + 1)
                avg_auprc_history[i] = cls_auprc_sum / (i + 1)
                print('\nAverage test accuracy until task', train_name, ':', avg_acc_history[i])
                print('Average test AUROC until task', train_name, ':', avg_auroc_history[i])
                print('Average test AUPRC until task', train_name, ':', avg_auprc_history[i])

            avg_acc_history_all_repeats.append(avg_acc_history)
            avg_auroc_history_all_repeats.append(avg_auroc_history)
            avg_auprc_history_all_repeats.append(avg_auprc_history)

            # Gather the final avg accuracy
            avg_final_acc[reg_coef][r] = avg_acc_history[-1]

            # Print the summary so far
            print('===Summary of experiment repeats:',r+1,'/',args.repeat,'===')
            print('The regularization coefficient:', args.reg_coef)
            print('The last avg acc of all repeats:', avg_final_acc[reg_coef])
            print('mean:', avg_final_acc[reg_coef].mean(), 'std:', avg_final_acc[reg_coef].std())

            end_time = time.time()
            time_elapsed = end_time - start_time
            times_per_run.append(time_elapsed)
            print('Time elapsed for this run:', round(time_elapsed, 2), 's')

        print('\nEpochs per run: ', epochs_per_run)
        print('Times per run: ', times_per_run)
        print('Runs: %d,  Average time per run: %.2f +/- %.2f s, %.1f +/- %.1f min' %
              (args.repeat, np.mean(np.array(times_per_run)), np.std(np.array(times_per_run)), np.mean(np.array(times_per_run)) / 60, np.std(np.array(times_per_run)) / 60))
        print('Runs: %d,  Average #epochs for all tasks: %.2f +/- %.2f' %
              (args.repeat, np.mean(np.array([sum(l) for l in epochs_per_run])), np.std(np.array([sum(l) for l in epochs_per_run]))))

        avg_acc_history_all_repeats = np.array(avg_acc_history_all_repeats)
        avg_auroc_history_all_repeats = np.array(avg_auroc_history_all_repeats)
        avg_auprc_history_all_repeats = np.array(avg_auprc_history_all_repeats)
        print('\nAccuracy after all repeats: ', avg_acc_history_all_repeats)
        print('AUROC after all repeats: ', avg_auroc_history_all_repeats)
        print('AUPRC after all repeats: ', avg_auprc_history_all_repeats)

    for reg_coef,v in avg_final_acc.items():
        print('\nreg_coef:', reg_coef,'mean:', avg_final_acc[reg_coef].mean(), 'std:', avg_final_acc[reg_coef].std())


    ### Plot values of acc, auroc and auprc for average values until every task
    num_tasks = len(task_names)
    min_y = 30
    colors = ['tab:blue', 'tab:orange', 'tab:green']

    mean_acc, std_acc = np.mean(avg_acc_history_all_repeats, axis=0), np.std(avg_acc_history_all_repeats, axis=0)
    mean_auroc, std_auroc = np.mean(avg_auroc_history_all_repeats, axis=0), np.std(avg_auroc_history_all_repeats, axis=0)
    mean_auprc, std_auprc = np.mean(avg_auprc_history_all_repeats, axis=0), np.std(avg_auprc_history_all_repeats, axis=0)

    end_performance = {i: {'acc': 0, 'auroc': 0, 'auprc': 0, 'std_acc': 0, 'std_auroc': 0, 'std_auprc': 0}
                       for i in range(num_tasks)}

    for i in range(num_tasks):
        end_performance[i]['acc'] = mean_acc[i]
        end_performance[i]['auroc'] = mean_auroc[i]
        end_performance[i]['auprc'] = mean_auprc[i]
        end_performance[i]['std_acc'] = std_acc[i]
        end_performance[i]['std_auroc'] = std_auroc[i]
        end_performance[i]['std_auprc'] = std_auprc[i]

    metrics = ['acc', 'auroc', 'auprc']  # possibilities: 'acc', 'auroc', 'auprc'
    print('Metrics at the end of each task training:\n', end_performance)
    plot_multiple_histograms(end_performance, num_tasks, metrics,
                             '#runs: %d, average task results, %s method, early stopping=%s (%s)' %
                             (args.repeat, args.agent_name, str(do_early_stopping), stopping_criteria),
                             colors[:len(metrics)], 'Metric value', min_y)



