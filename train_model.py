# Written by Dr Daniel Buscombe, Marda Science LLC
# for the USGS Coastal Change Hazards Program
#
# MIT License
#
# Copyright (c) 2021-22, Marda Science LLC
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import sys,os, time
# sys.path.insert(1, 'src')

import json
from tkinter import filedialog
from tkinter import *
from random import shuffle

###############################################################
## VARIABLES
###############################################################


root = Tk()
root.filename =  filedialog.askdirectory(initialdir = "/segmentation_zoo",title = "Select directory of data files")
data_path = root.filename
print(data_path)
root.withdraw()

root = Tk()
root.filename =  filedialog.askopenfilename(initialdir = data_path,title = "Select config file",filetypes = (("config files","*.json"),("all files","*.*")))
configfile = root.filename
print(configfile)
root.withdraw()


weights = configfile.replace('.json','.h5').replace('config', 'weights')

try:
    os.mkdir(os.path.dirname(weights))
except:
    pass

#---------------------------------------------------
with open(configfile) as f:
    config = json.load(f)

for k in config.keys():
    exec(k+'=config["'+k+'"]')

USE_GPU = True
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"

if USE_GPU == True:
    if 'SET_GPU' in locals():
        os.environ['CUDA_VISIBLE_DEVICES'] = str(SET_GPU)
    else:
        #use the first available GPU
        os.environ['CUDA_VISIBLE_DEVICES'] = '0' #'1'
else:
   ## to use the CPU (not recommended):
   os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

#suppress tensorflow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from doodleverse_utils.imports import *
#---------------------------------------------------

trainsamples_fig = weights.replace('.h5','_train_sample_batch.png').replace('weights', 'modelOut')
valsamples_fig = weights.replace('.h5','_val_sample_batch.png').replace('weights', 'modelOut')

hist_fig = weights.replace('.h5','_trainhist_'+str(BATCH_SIZE)+'.png').replace('weights', 'modelOut')

try:
    direc = os.path.dirname(hist_fig)
    print("Making new directory for example model outputs: %s"% (direc))
    os.mkdir(direc)
except:
    pass

test_samples_fig =  weights.replace('.h5','_val.png').replace('weights', 'modelOut')


###############################################################
### main
###############################################################
if USE_GPU == True:
    print('GPU name: ', tf.config.experimental.list_physical_devices('GPU'))
    print("Num GPUs Available: ", len(tf.config.experimental.list_physical_devices('GPU')))

#---------------------------------------------------
# learning rate function
def lrfn(epoch):
    """
    lrfn(epoch)
    This function creates a custom piecewise linear-exponential learning rate function for a custom learning rate scheduler. It is linear to a max, then exponentially decays

    * INPUTS: current `epoch` number
    * OPTIONAL INPUTS: None
    * GLOBAL INPUTS:`START_LR`, `MIN_LR`, `MAX_LR`, `RAMPUP_EPOCHS`, `SUSTAIN_EPOCHS`, `EXP_DECAY`
    * OUTPUTS:  the function lr with all arguments passed

    """
    def lr(epoch, START_LR, MIN_LR, MAX_LR, RAMPUP_EPOCHS, SUSTAIN_EPOCHS, EXP_DECAY):
        if epoch < RAMPUP_EPOCHS:
            lr = (MAX_LR - START_LR)/RAMPUP_EPOCHS * epoch + START_LR
        elif epoch < RAMPUP_EPOCHS + SUSTAIN_EPOCHS:
            lr = MAX_LR
        else:
            lr = (MAX_LR - MIN_LR) * EXP_DECAY**(epoch-RAMPUP_EPOCHS-SUSTAIN_EPOCHS) + MIN_LR
        return lr
    return lr(epoch, START_LR, MIN_LR, MAX_LR, RAMPUP_EPOCHS, SUSTAIN_EPOCHS, EXP_DECAY)


#-----------------------------------
def load_npz(example):
    # if N_DATA_BANDS==4:
    #     with np.load(example.numpy()) as data:
    #         image = data['arr_0'].astype('uint8')
    #         image = standardize(image)
    #         nir = data['arr_1'].astype('uint8')
    #         label = data['arr_2'].astype('uint8')
    #         #file = str(data['arr_2'])
    #     return image, nir,label#, file
    # else:
    with np.load(example.numpy()) as data:
        image = data['arr_0'].astype('uint8')
        image = standardize(image)
        label = data['arr_1'].astype('uint8')
        #file = str(data['arr_2'])
    return image, label#, file


@tf.autograph.experimental.do_not_convert
#-----------------------------------
def read_seg_dataset_multiclass(example):
    """
    "read_seg_dataset_multiclass(example)"
    This function reads an example from a npz file into a single image and label
    INPUTS:
        * dataset example object (filename of npz)
    OPTIONAL INPUTS: None
    GLOBAL INPUTS: TARGET_SIZE
    OUTPUTS:
        * image [tensor array]
        * class_label [tensor array]
    """
    # if N_DATA_BANDS==4:
    #     # image, nir, label, file = tf.py_function(func=load_npz, inp=[example], Tout=[tf.uint8, tf.uint8, tf.uint8, tf.string])
    #     image, nir, label = tf.py_function(func=load_npz, inp=[example], Tout=[tf.uint8, tf.uint8, tf.uint8])
    #     nir = tf.cast(nir, tf.float32)#/ 255.0
    # else:
    #image, label, file = tf.py_function(func=load_npz, inp=[example], Tout=[tf.float32, tf.uint8, tf.string])
    image, label = tf.py_function(func=load_npz, inp=[example], Tout=[tf.float32, tf.uint8])

    if NCLASSES==1:
        label = tf.expand_dims(label,-1)

    # if N_DATA_BANDS==4:
    #     image = tf.concat([image, tf.expand_dims(nir,-1)],-1)
    #     return image, label#, file
    # else:
    return image, label#, file


#-----------------------------------
def plotcomp_n_getiou(ds,model,NCLASSES, DOPLOT, test_samples_fig, subset,num_batches=10):

    class_label_colormap = ['#3366CC','#DC3912','#FF9900','#109618','#990099','#0099C6','#DD4477',
                            '#66AA00','#B82E2E', '#316395','#0d0887', '#46039f', '#7201a8',
                            '#9c179e', '#bd3786', '#d8576b', '#ed7953', '#fb9f3a', '#fdca26', '#f0f921']

    if NCLASSES>1:
        class_label_colormap = class_label_colormap[:NCLASSES]
    else:
        class_label_colormap = class_label_colormap[:NCLASSES+1]

    IOUc = []; Dc=[]; Kc = []

    counter = 0
    for i,l in ds.take(num_batches):

        for img,lbl in zip(i,l):

            img = standardize(img)

            try:
                est_label = model.predict(tf.expand_dims(img, 0) , batch_size=1)
            except:
                est_label = model.predict(tf.expand_dims(img[:,:,0], 0) , batch_size=1)


            iouscore = mean_iou_np(tf.expand_dims(tf.squeeze(lbl), 0), est_label)
            # print(iouscore)

            dicescore = mean_dice_np(tf.expand_dims(tf.squeeze(lbl), 0), est_label)
            # print(dicescore)

            kl = tf.keras.losses.KLDivergence()
            kld = kl(tf.expand_dims(tf.squeeze(lbl), 0), est_label).numpy()
            #print(kld)


            if NCLASSES==1:
                est_label = np.argmax(est_label.squeeze(), -1)
                est_label[est_label<.5] = 0
                est_label[est_label>.5] = 1
            else:
                est_label = np.argmax(est_label.squeeze(), -1)

            if NCLASSES==1:
                lbl = lbl.numpy().squeeze()
                lbl = np.argmax(lbl, -1)
            else:
                lbl = np.argmax(lbl.numpy(), -1)


            img = rescale_array(img.numpy(), 0, 1)

            color_estlabel = label_to_colors(est_label, tf.cast(img[:,:,0]==0,tf.uint8),
                                            alpha=128, colormap=class_label_colormap,
                                             color_class_offset=0, do_alpha=False)

            color_label = label_to_colors(lbl, tf.cast(img[:,:,0]==0,tf.uint8),
                                            alpha=128, colormap=class_label_colormap,
                                             color_class_offset=0, do_alpha=False)

            if DOPLOT:
                plt.subplot(221)
                if np.ndim(img)>=3:
                    plt.imshow(img[:,:,0], cmap='gray')
                else:
                    plt.imshow(img)#, cmap='gray')
                if NCLASSES==1:
                    plt.imshow(lbl, alpha=0.1, cmap=plt.cm.bwr, vmin=0, vmax=NCLASSES)
                else:
                    plt.imshow(color_label, alpha=0.5)#, cmap=plt.cm.bwr, vmin=0, vmax=NCLASSES-1)

                plt.axis('off')

                plt.subplot(222)
                if np.ndim(img)>=3:
                    plt.imshow(img[:,:,0], cmap='gray')
                else:
                    plt.imshow(img)#, cmap='gray')
                if NCLASSES==1:
                    plt.imshow(est_label, alpha=0.1, cmap=plt.cm.bwr, vmin=0, vmax=NCLASSES)
                else:
                    plt.imshow(color_estlabel, alpha=0.5)#, cmap=plt.cm.bwr, vmin=0, vmax=NCLASSES-1)

                plt.axis('off')
                plt.title('dice = '+str(dicescore)[:5]+', kl = '+str(kld)[:5], fontsize=6)
                IOUc.append(iouscore)
                Dc.append(dicescore)
                Kc.append(kld)

                del iouscore, dicescore, kld

                if subset=='val':
                    plt.savefig(test_samples_fig.replace('_val.png', '_val_'+str(counter)+'.png'),
                            dpi=200, bbox_inches='tight')
                else:
                    plt.savefig(test_samples_fig.replace('_val.png', '_train_'+str(counter)+'.png'),
                            dpi=200, bbox_inches='tight')

                plt.close('all')
            counter += 1
            K.clear_session()

    return IOUc, Dc, Kc


###==========================================================
#-------------------------------------------------
#uncomment to use all files instead
# filenames = tf.io.gfile.glob(data_path+os.sep+ROOT_STRING+'*.npz')

#uncomment to use non-augmented files instead
#filenames = tf.io.gfile.glob(data_path+os.sep+ROOT_STRING+'noaug*.npz')
# if len(filenames)==0:
#     filenames = tf.io.gfile.glob(data_path+os.sep+ROOT_STRING+'_noaug*.npz')

filenames = tf.io.gfile.glob(data_path+os.sep+ROOT_STRING+'aug*.npz')
if len(filenames)==0:
    filenames = tf.io.gfile.glob(data_path+os.sep+ROOT_STRING+'_aug*.npz')

try:
    dir_path = os.path.dirname(os.getcwd())
    os.mkdir(dir_path+os.sep+'weights')
except:
    pass # weights direc already exists

shuffle(filenames)

list_ds = tf.data.Dataset.list_files(filenames, shuffle=False)

val_size = int(len(filenames) * VALIDATION_SPLIT)

validation_steps = val_size // BATCH_SIZE
steps_per_epoch =  int(len(filenames) * 1-VALIDATION_SPLIT) // BATCH_SIZE

print(steps_per_epoch)
print(validation_steps)

train_ds = list_ds.skip(val_size)
val_ds = list_ds.take(val_size)

train_files = []
for i in train_ds:
    train_files.append(i.numpy().decode().split(os.sep)[-1])

val_files = []
for i in val_ds:
    val_files.append(i.numpy().decode().split(os.sep)[-1])

try:
    np.savetxt(weights.replace('.h5','_train_files.txt'), train_files, fmt='%s')
except:
    dir_path = os.path.dirname(os.path.realpath(weights))
    os.mkdir(dir_path)
    np.savetxt(weights.replace('.h5','_train_files.txt'), train_files, fmt='%s')


np.savetxt(weights.replace('.h5','_val_files.txt'), val_files, fmt='%s')

# Set `num_parallel_calls` so multiple images are loaded/processed in parallel.
train_ds = train_ds.map(read_seg_dataset_multiclass, num_parallel_calls=AUTO)
train_ds = train_ds.repeat()
train_ds = train_ds.batch(BATCH_SIZE, drop_remainder=True) # drop_remainder will be needed on TPU
train_ds = train_ds.prefetch(AUTO) #

val_ds = val_ds.map(read_seg_dataset_multiclass, num_parallel_calls=AUTO)
val_ds = val_ds.repeat()
val_ds = val_ds.batch(BATCH_SIZE, drop_remainder=True) # drop_remainder will be needed on TPU
val_ds = val_ds.prefetch(AUTO) #


#
# ## uncommant to view examples
# class_label_colormap = ['#3366CC','#DC3912','#FF9900','#109618','#990099','#0099C6','#DD4477',
#                         '#66AA00','#B82E2E', '#316395','#0d0887', '#46039f', '#7201a8',
#                         '#9c179e', '#bd3786', '#d8576b', '#ed7953', '#fb9f3a', '#fdca26', '#f0f921']
#
# if NCLASSES>1:
#     class_label_colormap = class_label_colormap[:NCLASSES]
# else:
#     class_label_colormap = class_label_colormap[:NCLASSES+1]
#
# for imgs,lbls in train_ds.take(1):
#   for count,(im,lab) in enumerate(zip(imgs, lbls)):
#      print(im.shape)
#      if im.shape[-1]>3:
#          plt.imshow(im[:,:,:3])
#      else:
#          plt.imshow(im)
#
#      print(lab.shape)
#      lab = np.argmax(lab.numpy().squeeze(),-1)
#      print(np.unique(lab))
#
#      color_label = label_to_colors(np.squeeze(lab), tf.cast(im[:,:,0]==0,tf.uint8),
#                                     alpha=128, colormap=class_label_colormap,
#                                      color_class_offset=0, do_alpha=False)
#
#      if NCLASSES==1:
#          plt.imshow(color_label, alpha=0.75, vmin=0, vmax=NCLASSES)
#      else:
#          plt.imshow(color_label,  alpha=0.75, vmin=0, vmax=NCLASSES)
#
#      plt.axis('off')
#      #plt.show()
#      plt.savefig('example-{}.png'.format(count), dpi=200)


##===============================================
print('.....................................')
print('Creating and compiling model ...')

if MODEL =='resunet':
    model =  custom_resunet((TARGET_SIZE[0], TARGET_SIZE[1], N_DATA_BANDS),
                    FILTERS,
                    nclasses=[NCLASSES+1 if NCLASSES==1 else NCLASSES][0],
                    kernel_size=(KERNEL,KERNEL),
                    strides=STRIDE,
                    dropout=DROPOUT,#0.1,
                    dropout_change_per_layer=DROPOUT_CHANGE_PER_LAYER,#0.0,
                    dropout_type=DROPOUT_TYPE,#"standard",
                    use_dropout_on_upsampling=USE_DROPOUT_ON_UPSAMPLING
                    )
elif MODEL=='unet':
    model =  custom_unet((TARGET_SIZE[0], TARGET_SIZE[1], N_DATA_BANDS),
                    FILTERS,
                    nclasses=[NCLASSES+1 if NCLASSES==1 else NCLASSES][0],
                    kernel_size=(KERNEL,KERNEL),
                    strides=STRIDE,
                    dropout=DROPOUT,#0.1,
                    dropout_change_per_layer=DROPOUT_CHANGE_PER_LAYER,#0.0,
                    dropout_type=DROPOUT_TYPE,#"standard",
                    use_dropout_on_upsampling=USE_DROPOUT_ON_UPSAMPLING,#False,
                    )

elif MODEL =='simple_resunet':

    model = simple_resunet((TARGET_SIZE[0], TARGET_SIZE[1], N_DATA_BANDS),
                kernel = (2, 2),
                num_classes=[NCLASSES+1 if NCLASSES==1 else NCLASSES][0],
                activation="relu",
                use_batch_norm=True,
                dropout=DROPOUT,#0.1,
                dropout_change_per_layer=DROPOUT_CHANGE_PER_LAYER,#0.0,
                dropout_type=DROPOUT_TYPE,#"standard",
                use_dropout_on_upsampling=USE_DROPOUT_ON_UPSAMPLING,#False,
                filters=FILTERS,#8,
                num_layers=4,
                strides=(1,1))
#346,564
elif MODEL=='simple_unet':
    model = simple_unet((TARGET_SIZE[0], TARGET_SIZE[1], N_DATA_BANDS),
                kernel = (2, 2),
                num_classes=[NCLASSES+1 if NCLASSES==1 else NCLASSES][0],
                activation="relu",
                use_batch_norm=True,
                dropout=DROPOUT,#0.1,
                dropout_change_per_layer=DROPOUT_CHANGE_PER_LAYER,#0.0,
                dropout_type=DROPOUT_TYPE,#"standard",
                use_dropout_on_upsampling=USE_DROPOUT_ON_UPSAMPLING,#False,
                filters=FILTERS,#8,
                num_layers=4,
                strides=(1,1))
#242,812

elif MODEL=='satunet':
    #model = sat_unet((TARGET_SIZE[0], TARGET_SIZE[1], N_DATA_BANDS), num_classes=NCLASSES)

    model = custom_satunet((TARGET_SIZE[0], TARGET_SIZE[1], N_DATA_BANDS),
                kernel = (2, 2),
                num_classes=[NCLASSES+1 if NCLASSES==1 else NCLASSES][0],
                activation="relu",
                use_batch_norm=True,
                dropout=DROPOUT,#0.1,
                dropout_change_per_layer=DROPOUT_CHANGE_PER_LAYER,#0.0,
                dropout_type=DROPOUT_TYPE,#"standard",
                use_dropout_on_upsampling=USE_DROPOUT_ON_UPSAMPLING,#False,
                filters=FILTERS,#8,
                num_layers=4,
                strides=(1,1))

else:
    print("Model must be one of 'unet', 'resunet', or 'satunet'")
    sys.exit(2)

# Open the file
with open(MODEL+'_report.txt','w') as fh:
    # Pass the file handle in as a lambda function to make it callable
    model.summary(print_fn=lambda x: fh.write(x + '\n'))

if LOSS=='hinge':
    model.compile(optimizer = 'adam', loss =tf.keras.losses.CategoricalHinge(), metrics = [mean_iou, dice_coef])
elif LOSS=='dice':
    model.compile(optimizer = 'adam', loss =dice_coef_loss, metrics = [mean_iou, dice_coef])
elif LOSS.startswith('cat'):
    model.compile(optimizer = 'adam', loss =tf.keras.losses.CategoricalCrossentropy(), metrics = [mean_iou, dice_coef])
elif LOSS.startswith('k'):
    model.compile(optimizer = 'adam', loss =tf.keras.losses.KLDivergence(), metrics = [mean_iou, dice_coef])


if MODEL =='resunet':
    try:
        tf.keras.utils.plot_model(model,to_file="residual_unet_test.png",dpi=200)
    except:
        pass
elif MODEL=='unet':
    try:
        tf.keras.utils.plot_model(model,to_file="unet_test.png",dpi=200)
    except:
        pass
earlystop = EarlyStopping(monitor="val_loss",
                              mode="min", patience=PATIENCE)

# set checkpoint file
model_checkpoint = ModelCheckpoint(weights, monitor='val_loss',
                                verbose=0, save_best_only=True, mode='min',
                                save_weights_only = True)

# models are sensitive to specification of learning rate. How do you decide? Answer: you don't. Use a learning rate scheduler
lr_callback = tf.keras.callbacks.LearningRateScheduler(lambda epoch: lrfn(epoch), verbose=True)

callbacks = [model_checkpoint, earlystop, lr_callback]


if DO_TRAIN:
    print('.....................................')
    print('Training model ...')
    history = model.fit(train_ds, steps_per_epoch=steps_per_epoch, epochs=MAX_EPOCHS,
                          validation_data=val_ds, validation_steps=validation_steps,
                          callbacks=callbacks)

    # Plot training history
    plot_seg_history_iou(history, hist_fig)

    plt.close('all')
    K.clear_session()

    model.save(weights.replace('.h5','_fullmodel.h5'))

    np.savez_compressed(weights.replace('.h5','_model_history.npz'),**history.history)

else:
    try:
        model = tf.keras.models.load_model(weights.replace('.h5','_fullmodel.h5'))
    except:
        model.load_weights(weights)



# # ##########################################################
# ### evaluate
print('.....................................')
print('Evaluating model on entire validation set ...')
# # testing
scores = model.evaluate(val_ds, steps=validation_steps)

print('loss={loss:0.4f}, Mean IOU={mean_iou:0.4f}, Mean Dice={mean_dice:0.4f}'.format(loss=scores[0], mean_iou=scores[1], mean_dice=scores[2]))

# # # ##########################################################


IOUc, Dc, Kc = plotcomp_n_getiou(val_ds,model,NCLASSES,DOPLOT,test_samples_fig,'val')
print('Mean of mean IoUs (validation subset)={mean_iou:0.3f}'.format(mean_iou=np.mean(IOUc)))
print('Mean of mean Dice scores (validation subset)={mean_dice:0.3f}'.format(mean_dice=np.mean(Dc)))
print('Mean of mean KLD scores (validation subset)={mean_kld:0.3f}'.format(mean_kld=np.mean(Kc)))


IOUc, Dc, Kc = plotcomp_n_getiou(train_ds,model,NCLASSES,DOPLOT,test_samples_fig,'train')
print('Mean of mean IoUs (train subset)={mean_iou:0.3f}'.format(mean_iou=np.mean(IOUc)))
print('Mean of mean Dice scores (train subset)={mean_dice:0.3f}'.format(mean_dice=np.mean(Dc)))
print('Mean of mean KLD scores (train subset)={mean_kld:0.3f}'.format(mean_kld=np.mean(Kc)))

#
# plt.plot(Dc, Kc, 'ko')
# plt.savefig('D_vs_KL.png', dpi=200)
# plt.close()
