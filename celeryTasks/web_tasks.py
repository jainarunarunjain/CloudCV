"""
This file caters to all the jobs for the web server.

Author - Prashant Jalan
"""

from __future__ import absolute_import
from celeryTasks.celery import app

#Establishing connection to send results and write messages
import redis, json
rs = redis.StrictRedis(host='redis', port=6379)


# The function takes as input:
# 1) src_path: Input image, directory, or npy. 
# 2) socketid: The socket id of the connection.
# 3) result_path: The folder path where the result image will be stored.
#    It should be full path in case of a single file, else the directory path.
# NOTE:
# 1) Its job is to classify the images according to the pre-trained model.
# 2) ignore_result=True signifies that celery won't pass any result to the backend.
# 3) It is important to import all the modules only inside the function
# 4) When running with new version of caffe do np.load(MEAN_FILE).mean(1).mean(1)
@app.task(ignore_result=True)
def classifyImages(src_path, socketid, result_path):
	try:
		import caffe, numpy as np, os, glob, time, operator, scipy.io as sio

		#Used to assign labels to the results
		matWNID = sio.loadmat(os.path.join(os.path.dirname(__file__),'WNID.mat'))
		WNID_cells = matWNID['wordsortWNID']

		#Caffe Initialisations
		CAFFE_DIR = os.path.normpath(os.path.join(os.path.dirname(caffe.__file__),"..",".."))
		MODEL_FILE = os.path.join(CAFFE_DIR, 'models/bvlc_reference_caffenet/deploy.prototxt')
		PRETRAINED = os.path.join(CAFFE_DIR, 'models/bvlc_reference_caffenet/bvlc_reference_caffenet.caffemodel')
		MEAN_FILE = os.path.join(CAFFE_DIR, 'python/caffe/imagenet/ilsvrc_2012_mean.npy')
		RAW_SCALE = 255.0
		IMAGE_DIMS = (256, 256)
		CHANNEL_SWAP = (2, 1, 0)

		#Set CPU mode
		caffe.set_mode_cpu()

		# Make classifier.
		classifier = caffe.Classifier(MODEL_FILE, PRETRAINED, image_dims=IMAGE_DIMS, 
		mean=np.load(MEAN_FILE).mean(1).mean(1), raw_scale=RAW_SCALE,
		channel_swap=CHANNEL_SWAP)

		# Load numpy array (.npy), directory glob (*), or image file.
		input_file = os.path.abspath(src_path)
		if input_file.endswith('npy'):
			inputs = np.load(args.input_file)
		elif os.path.isdir(input_file):
			inputs = [caffe.io.load_image(im_f) for im_f in glob.glob(input_file + '/*') if os.path.isfile(im_f)]
		else:
			inputs = [caffe.io.load_image(input_file)]

		# Classify.
		start = time.time()
		prediction = classifier.predict(inputs)
		timeMsg = "Completed in %.2f s." % (time.time() - start)
		rs.publish('chat', json.dumps({'message': timeMsg, 'socketid': str(socketid)}))

		#Send Results
		if os.path.isdir(input_file):
			count = 0
			for im_f in glob.glob(input_file + '/*'):
				if os.path.isfile(im_f):
					dictionary = {}
					for i, j in enumerate(prediction[count]):
						dictionary[i] = j
					predsorted = sorted(dictionary.iteritems(), key=operator.itemgetter(1), reverse=True)
					top5 = predsorted[0:5]
					topresults = []
					for item in top5:
						topresults.append([str(WNID_cells[item, 0][0][0]),str(item[1])])
					count += 1

					web_result = {}
					web_result[os.path.join(result_path, os.path.basename(im_f))] = topresults
					rs.publish('chat', json.dumps({'web_result': json.dumps(web_result), 'socketid': str(socketid)}))
		
		else:
			dictionary = {}
			for i, j in enumerate(prediction[0]):
				dictionary[i] = j
			predsorted = sorted(dictionary.iteritems(), key=operator.itemgetter(1), reverse=True)
			top5 = predsorted[0:5]
			topresults = [] 
			for item in top5:
				topresults.append([str(WNID_cells[item, 0][0][0]),str(item[1])])

			web_result = {}
			web_result[result_path] = topresults
			rs.publish('chat', json.dumps({'web_result': json.dumps(web_result), 'socketid': str(socketid)}))
		
		rs.publish('chat', json.dumps({'message': 'Thank you for using CloudCV', 'socketid': str(socketid)}))

	except Exception as e:
		#In case of an error, print the whole error with traceback
		import traceback
		rs.publish('chat', json.dumps({'message': str(traceback.format_exc()), 'socketid': str(socketid)}))


"""
The function takes as input:
1) src_path: Input image or directory.
2) socketid: The socket id of the connection.
3) result_path: Directory where the mat files are to be stored.

NOTE:
1) Its job is to find the decaf features of images according to the pre-trained model.
2) ignore_result=True signifies that celery won't pass any result to the backend.
3) log_to_terminal is used to publish messages to the redis server.
4) It is important to import all the modules only inside the function
5) When running with new version of caffe do np.load(MEAN_FILE).mean(1).mean(1)
"""
@app.task(ignore_result=True)
def decafImages(src_path, result_path, socketid):
	try:
		import caffe, numpy as np, os, glob, time, operator, scipy.io as sio

		#Caffe Initialisations
		CAFFE_DIR = os.path.normpath(os.path.join(os.path.dirname(caffe.__file__),"..",".."))
		MODEL_FILE = os.path.join(CAFFE_DIR, 'models/bvlc_reference_caffenet/deploy.prototxt')
		PRETRAINED = os.path.join(CAFFE_DIR, 'models/bvlc_reference_caffenet/bvlc_reference_caffenet.caffemodel')

		#Set CPU mode
		caffe.set_mode_cpu()

		# Make classifier.
		classifier = caffe.Classifier(MODEL_FILE, PRETRAINED)

		print "Made Classifer"
		#Find decaf features and send Results
		if os.path.isdir(src_path):
			for input_file in glob.glob(src_path + '/*'):
				if os.path.isfile(input_file):
					print "Here 1"
					rs.publish('chat', json.dumps({'message': 'Processing '+os.path.basename(input_file), 'socketid': str(socketid)}))

					#Loading Image
					input_image = caffe.io.load_image(input_file)
					print "Here 2"
					#Finding decaf features
					start = time.time()
					classifier.predict([input_image])
					blobs = classifier.blobs.items()
					features = blobs[-3][1].data[:,:,0,0]
					features_center = blobs[-3][1].data[4,:,0,0]
					features_center = np.resize(features_center, (1,4096))
					timeMsg = "Completed in %.2f s." % (time.time() - start)
					rs.publish('chat', json.dumps({'message': timeMsg, 'socketid': str(socketid)}))
					print "Here 3"
					#Saving decaf features
					matfile = {}
					matfile['decaf'] = features
					matfile['decaf_center'] = features_center
					out_file = os.path.join(result_path, os.path.basename(input_file)+'.mat')
					sio.savemat(out_file, matfile)
					r.publish('chat', json.dumps({'web_result': out_file, 'socketid': str(socketid)}))
		else:
			print "Here 5"
			input_file = src_path

			rs.publish('chat', json.dumps({'message': 'Processing '+os.path.basename(input_file), 'socketid': str(socketid)}))
			
			#Loading Image
			input_image = caffe.io.load_image(input_file)
			print "Here 6"
			#Finding decaf features
			start = time.time()
			classifier.predict([input_image])
			blobs = classifier.blobs.items()
			features = blobs[-3][1].data[:,:,0,0]
			features_center = blobs[-3][1].data[4,:,0,0]
			features_center = np.resize(features_center, (1,4096))
			timeMsg = "Completed in %.2f s." % (time.time() - start)
			rs.publish('chat', json.dumps({'message': timeMsg, 'socketid': str(socketid)}))
			print "Here 7"
			#Saving decaf features
			matfile = {}
			matfile['decaf'] = features
			matfile['decaf_center'] = features_center
			out_file = os.path.join(result_path, os.path.basename(input_file)+'.mat')
			sio.savemat(out_file, matfile)
			r.publish('chat', json.dumps({'web_result': out_file, 'socketid': str(socketid)}))
		print "Here 8"
		rs.publish('chat', json.dumps({'message': 'Thank you for using CloudCV', 'socketid': str(socketid)}))

	except Exception as e:
		#In case of an error, print the whole error with traceback
		import traceback
		rs.publish('chat', json.dumps({'message': str(traceback.format_exc()), 'socketid': str(socketid)}))
