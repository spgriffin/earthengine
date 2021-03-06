#! /usr/bin/env python
import time, math, sys
import ee
from flask import Flask, render_template, request
from eeMad import imad
from eeWishart import omnibus

# Set to True for localhost, False for appengine dev_appserver or deploy
#------------
local = True
#------------

glbls = {'centerLon':8.5,'centerLat':50.05,'minLat':49.985,'maxLat':50.078,'minLon':8.444,'maxLon':8.682}
zoom = 10
jet = 'black,blue,cyan,yellow,red'

if local:
# for local flask server
    ee.Initialize()
    msg = 'Choose a rectangular region'
    sentinel1 = 'sentinel1.html'
    sentinel2 = 'sentinel2.html'
    mad1 = 'mad.html'
    omnibus1 = 'omnibus.html'
else:
# for appengine deployment or development appserver
    import config
    msg = 'Choose a SMALL rectangular region'
    ee.Initialize(config.EE_CREDENTIALS, 'https://earthengine.googleapis.com')
    sentinel1 = 'sentinel1web.html'
    sentinel2 = 'sentinel2web.html'
    mad = 'madweb.html'
    omnibus = 'omnibusweb.html'    

app = Flask(__name__)

def iterate(image1,image2,niter,first):
#   simulated iteration of MAD for debugging
    for i in range(1,niter+1):
        result = ee.Dictionary(imad(i,first))
        allrhos = ee.List(result.get('allrhos'))
        chi2 = ee.Image(result.get('chi2'))
        MAD = ee.Image(result.get('MAD'))
        first = ee.Dictionary({'image':image1.addBands(image2),
                               'allrhos':allrhos,
                               'chi2':chi2,
                               'MAD':MAD})
    return result

#------------------
# helper functions
#------------------

def get_vv(image):   
    ''' get 'VV' band from sentinel-1 imageCollection and restore linear signal from db-values '''
    return image.select('VV').multiply(ee.Image.constant(math.log(10.0)/10.0)).exp()

def get_vh(image):   
    ''' get 'VH' band from sentinel-1 imageCollection and restore linear signal from db-values '''
    return image.select('VH').multiply(ee.Image.constant(math.log(10.0)/10.0)).exp()

def get_vvvh(image):   
    ''' get 'VV' and 'VH' bands from sentinel-1 imageCollection and restore linear signal from db-values '''
    return image.select('VV','VH').multiply(ee.Image.constant(math.log(10.0)/10.0)).exp()

def get_hh(image):   
    ''' get 'HH' band from sentinel-1 imageCollection and restore linear signal from db-values '''
    return image.select('HH').multiply(ee.Image.constant(math.log(10.0)/10.0)).exp()

def get_hv(image):   
    ''' get 'HV' band from sentinel-1 imageCollection and restore linear signal from db-values '''
    return image.select('HV').multiply(ee.Image.constant(math.log(10.0)/10.0)).exp()

def get_hhhv(image):   
    ''' get 'HH' and 'HV' bands from sentinel-1 imageCollection and restore linear signal from db-values '''
    return image.select('HH','HV').multiply(ee.Image.constant(math.log(10.0)/10.0)).exp()

def get_image(current,image):
    ''' accumulate a single image from a collection of images '''
    return ee.Image.cat(ee.Image(image),current)    
    
def clipList(current,prev):
    ''' clip a list of images '''
    imlist = ee.List(ee.Dictionary(prev).get('imlist'))
    rect = ee.Dictionary(prev).get('rect')    
    imlist = imlist.add(ee.Image(current).clip(rect))
    return ee.Dictionary({'imlist':imlist,'rect':rect})

def makefeature(data):
    ''' for exporting as CSV to Drive '''
    return ee.Feature(None, {'data': data})

#--------------------
# request handlers
#--------------------

@app.route('/')
def index():
    return app.send_static_file('index.html')
    
@app.route('/sentinel1.html', methods = ['GET', 'POST'])
def Sentinel1():    
    global glbls, msg, local, zoom
    if request.method == 'GET':
        return render_template(sentinel1, msg = msg,
                                          minLat = glbls['minLat'],
                                          minLon = glbls['minLon'],
                                          maxLat = glbls['maxLat'],
                                          maxLon = glbls['maxLon'],
                                          centerLon = glbls['centerLon'],
                                          centerLat = glbls['centerLat'],
                                          zoom = zoom)
    else:
        try: 
            startdate = request.form['startdate']  
            enddate = request.form['enddate']
            orbitpass = request.form['pass']
            polarization1 = request.form['polarization']
            relativeorbitnumber = request.form['relativeorbitnumber']
            if polarization1 == 'VV,VH':
                polarization = ['VV','VH']
            elif polarization1 == 'HH,HV':
                polarization = ['HH','HV']
            else:
                polarization = polarization1
            minLat = float(request.form['minLat'])
            minLon = float(request.form['minLon'])
            maxLat = float(request.form['maxLat'])
            maxLon = float(request.form['maxLon'])
            if request.form.has_key('export'):        
                export = request.form['export']
                gdexportname = request.form['exportname']
                gdexportscale = float(request.form['gdexportscale'])
            else:
                export = 'none'           
            if request.form.has_key('slanes'):        
                slanes = True  
            else:
                slanes = False  
            start = ee.Date(startdate)
            finish = ee.Date(enddate)    
            rect = ee.Geometry.Rectangle(minLon,minLat,maxLon,maxLat)     
            centerLon = (minLon + maxLon)/2.0
            centerLat = (minLat + maxLat)/2.0 
            ulPoint = ee.Geometry.Point([minLon,maxLat])   
            lrPoint = ee.Geometry.Point([maxLon,minLat])
            collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
                        .filterBounds(ulPoint) \
                        .filterBounds(lrPoint) \
                        .filterDate(start, finish) \
                        .filter(ee.Filter.eq('transmitterReceiverPolarisation', polarization)) \
                        .filter(ee.Filter.eq('resolution_meters', 10)) \
                        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
                        .filter(ee.Filter.eq('orbitProperties_pass', orbitpass))                        
            if relativeorbitnumber != '':
                collection = collection.filter(ee.Filter.eq('relativeOrbitNumber_start', int(relativeorbitnumber))) 
            collection = collection.sort('system:time_start')                             
            systemids =  str(ee.List(collection.aggregate_array('system:id')).getInfo())                            
            acquisition_times = ee.List(collection.aggregate_array('system:time_start')).getInfo()                                           
            count = len(acquisition_times)
            if count==0:
                raise ValueError('No images found')   
            timestamplist = []
            for timestamp in acquisition_times:
                tmp = time.gmtime(int(timestamp)/1000)
                timestamplist.append(time.strftime('%c', tmp))
            timestamp = timestamplist[0]    
            timestamps = str(timestamplist)      
            relativeorbitnumbers = str(ee.List(collection.aggregate_array('relativeOrbitNumber_start')).getInfo())                                                       
            image = ee.Image(collection.first())                       
            systemid = image.get('system:id').getInfo()  
            projection = image.select(0).projection().getInfo()['crs']      
#          make into collection of VV, VH or VVVH images and restore linear scale             
            if polarization1 == 'VV':
                pcollection = collection.map(get_vv)
            elif polarization1 == 'VH':
                pcollection = collection.map(get_vh)
            elif polarization1 == 'VV,VH':
                pcollection = collection.map(get_vvvh)
            elif polarization1 == 'HH':
                pcollection = collection.map(get_hh)
            elif polarization1 == 'HV':
                pcollection = collection.map(get_hv)
            elif polarization1 == 'HH,HV':
                pcollection = collection.map(get_hhhv)    
#          clipped image for display on map                
            if slanes:
#              just want max for shipping lanes
                outimage = pcollection.max().clip(rect)
                mapidclip = outimage.select(0).getMapId({'min': 0, 'max':1, 'opacity': 0.7})
                mapid = image.select(0).getMapId({'min': 0, 'max':1, 'opacity': 0.5})
                downloadtext = 'Download maximum intensity image'
                titletext = 'Sentinel-1 Maximum Intensity Image'
            else:
#              want the entire time series 
                mapid = image.select(0).getMapId({'min': 0, 'max':1, 'opacity': 0.5})
                image1clip = ee.Image(pcollection.first()).clip(rect)   
                mapidclip = image1clip.select(0).getMapId({'min': 0, 'max':1, 'opacity': 0.7})    
                downloadtext = 'Download image collection intersection'      
                titletext = 'Sentinel-1 Intensity Image'                                                      
#              clip the image collection and create a single multiband image      
                outimage = ee.Image(pcollection.iterate(get_image,image1clip))    
                                               
            if export == 'export':
#              export to Google Drive -------------------------
                gdexport = ee.batch.Export.image.toDrive(outimage,
                                                         description='driveExportTask', 
                                                         folder = 'EarthEngineImages',
                                                         fileNamePrefix=gdexportname,scale=gdexportscale,maxPixels=1e9)                
                
                gdexportid = str(gdexport.id)
                print >> sys.stderr, '****Exporting to Google Drive, task id: %s '%gdexportid
                gdexport.start() 
            else:
                gdexportid = 'none'
#              --------------------------------------------------                                        
            downloadpathclip =  outimage.getDownloadUrl({'scale':10})       
            
            glbls['minLat'] = minLat
            glbls['minLon'] = minLon
            glbls['maxLat'] = maxLat
            glbls['maxLon'] = maxLon  
            glbls['centerLon'] = centerLon
            glbls['centerLat'] = centerLat        
                                                                    
            return render_template('sentinel1out.html',
                                    mapid = mapid['mapid'],
                                    token = mapid['token'],
                                    mapidclip = mapidclip['mapid'], 
                                    tokenclip = mapidclip['token'], 
                                    centerLon = centerLon,
                                    centerLat = centerLat,
                                    zoom = zoom,
                                    downloadtext = downloadtext,
                                    titletext = titletext,
                                    downloadpathclip = downloadpathclip, 
                                    projection = projection,
                                    systemid = systemid,
                                    count = count,
                                    timestamp = timestamp,
                                    gdexportid = gdexportid,
                                    timestamps = timestamps,
                                    systemids = systemids,
                                    polarization = polarization1,
                                    relativeorbitnumbers = relativeorbitnumbers)  
        except Exception as e:
            return '<br />An error occurred in Sentinel1: %s'%e
                  

@app.route('/sentinel2.html', methods = ['GET', 'POST'])
def Sentinel2():
    global glbls, msg, local, zoom
    if request.method == 'GET':
        return render_template(sentinel2, msg = msg,
                                          minLat = glbls['minLat'],
                                          minLon = glbls['minLon'],
                                          maxLat = glbls['maxLat'],
                                          maxLon = glbls['maxLon'],
                                          centerLon = glbls['centerLon'],
                                          centerLat = glbls['centerLat'],
                                          zoom = zoom)
    else:
        try:
            startdate = request.form['startdate']  
            enddate = request.form['enddate']
            minLat = float(request.form['minLat'])
            minLon = float(request.form['minLon'])
            maxLat = float(request.form['maxLat'])
            maxLon = float(request.form['maxLon'])
            if request.form.has_key('export'):        
                export = request.form['export']
                gdexportname = request.form['exportname'] 
                gdexportscale = float(request.form['gdexportscale']) 
            else:
                export = ' '          
            start = ee.Date(startdate)
            finish = ee.Date(enddate)           
            rect = ee.Geometry.Rectangle(minLon,minLat,maxLon,maxLat)     
            centerLon = (minLon + maxLon)/2.0
            centerLat = (minLat + maxLat)/2.0 
            ulPoint = ee.Geometry.Point([minLon,maxLat])   
            lrPoint = ee.Geometry.Point([maxLon,minLat]) 
            collection = ee.ImageCollection('COPERNICUS/S2') \
                        .filterBounds(ulPoint) \
                        .filterBounds(lrPoint) \
                        .filterDate(start, finish) \
                        .sort('CLOUD_COVERAGE_ASSESSMENT', True) 
            acquisition_times = ee.List(collection.aggregate_array('system:time_start')).getInfo()                         
            count = collection.toList(100).length().getInfo()    
            if count==0:
                raise ValueError('No images found')        
            sensingorbitnumbers = str(ee.List(collection.aggregate_array('SENSING_ORBIT_NUMBER')).getInfo())
            
            timestamplist = []
            for timestamp in acquisition_times:
                tmp = time.gmtime(int(timestamp)/1000)
                timestamplist.append(time.strftime('%c', tmp))
            timestamp = timestamplist[0]    
            timestamps = str(timestamplist)   
            
            image = ee.Image(collection.first())         
            imageclip = image.clip(rect)              
            systemid = image.get('system:id').getInfo()
            cloudcover = image.get('CLOUD_COVERAGE_ASSESSMENT').getInfo()
            projection = image.select('B2').projection().getInfo()['crs']
            downloadpath = image.getDownloadUrl({'scale':30,'crs':projection})    
            if export == 'export':
#              export to Google Drive --------------------------
                gdexport = ee.batch.Export.image.toDrive(imageclip.select('B2','B3','B4','B8'),
                                         description='driveExportTask', 
                                         folder = 'EarthEngineImages',
                                         fileNamePrefix=gdexportname,scale=gdexportscale,maxPixels=1e9) 
                
                
                gdexportid = str(gdexport.id)
                print >> sys.stderr, '****Exporting to Google Drive, task id: %s '%gdexportid
                gdexport.start() 
            else:
                gdexportid = 'none'
#              --------------------------------------------------                    
            downloadpathclip = imageclip.select('B2','B3','B4','B8').getDownloadUrl({'scale':10, 'crs':projection})
            rgb = image.select('B2','B3','B4')            
            rgbclip = imageclip.select('B2','B3','B4')                 
            mapid = rgb.getMapId({'min':0, 'max':2000, 'opacity': 0.6}) 
            mapidclip = rgbclip.getMapId({'min':0, 'max':3000, 'opacity': 1.0}) 
            
            glbls['minLat'] = minLat
            glbls['minLon'] = minLon
            glbls['maxLat'] = maxLat
            glbls['maxLon'] = maxLon  
            glbls['centerLon'] = centerLon
            glbls['centerLat'] = centerLat  
                                 
            return render_template('sentinel2out.html',
                                    mapidclip = mapidclip['mapid'], 
                                    tokenclip = mapidclip['token'], 
                                    mapid = mapid['mapid'], 
                                    token = mapid['token'], 
                                    centerLon = centerLon,
                                    centerLat = centerLat,
                                    zoom = zoom,
                                    downloadtext = 'Download image intersection',
                                    downloadpath = downloadpath, 
                                    downloadpathclip = downloadpathclip, 
                                    systemid = systemid,
                                    cloudcover = cloudcover,
                                    projection = projection,
                                    count = count,
                                    sensingorbitnumbers = sensingorbitnumbers,
                                    timestamps = timestamps,
                                    timestamp = timestamp)  
        except Exception as e:
            return '<br />An error occurred in Sentinel2: %s'%e  
        
@app.route('/mad.html', methods = ['GET', 'POST'])
def Mad():
    global glbls, msg, local, zoom
    if request.method == 'GET':
        return render_template(mad1, msg = msg,
                                    minLat = glbls['minLat'],
                                    minLon = glbls['minLon'],
                                    maxLat = glbls['maxLat'],
                                    maxLon = glbls['maxLon'],
                                    centerLon = glbls['centerLon'],
                                    centerLat = glbls['centerLat'],
                                    zoom = zoom)
    else:
        try:
            hint = '(enable export to bypass)' 
            niter = int(request.form['iterations'])
            start1 = ee.Date(request.form['startdate1'])
            finish1 = ee.Date(request.form['enddate1'])
            start2 = ee.Date(request.form['startdate2'])
            finish2 = ee.Date(request.form['enddate2'])   
            minLat = float(request.form['minLat'])
            minLon = float(request.form['minLon'])
            maxLat = float(request.form['maxLat'])
            maxLon = float(request.form['maxLon'])
            platform = request.form['platform']
            if request.form.has_key('assexport'):        
                assexportscale = float(request.form['assexportscale'])
                assexportname = request.form['assexportname']
                assexport = request.form['assexport']
            else:
                assexport = 'none'
            if request.form.has_key('gdexport'):  
                gdexportscale = float(request.form['gdexportscale'])  
                gdexportname = request.form['gdexportname']    
                gdexport = request.form['gdexport']
            else:
                gdexport = 'none'                 
            rect = ee.Geometry.Rectangle(minLon,minLat,maxLon,maxLat)     
            centerLon = (minLon + maxLon)/2.0
            centerLat = (minLat + maxLat)/2.0 
            ulPoint = ee.Geometry.Point([minLon,maxLat])   
            lrPoint = ee.Geometry.Point([maxLon,minLat]) 
            if platform=='sentinel2':
                collection = ee.ImageCollection('COPERNICUS/S2') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start1, finish1) \
                            .sort('CLOUDY_PIXEL_PERCENTAGE', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for first time interval')        
                image1 = ee.Image(collection.first()).clip(rect).select('B2','B3','B4','B8')               
                timestamp1 = ee.Date(image1.get('system:time_start')).getInfo()
                timestamp1 = time.gmtime(int(timestamp1['value'])/1000)
                timestamp1 = time.strftime('%c', timestamp1) 
                systemid1 = image1.get('system:id').getInfo()
                cloudcover1 = image1.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
                collection = ee.ImageCollection('COPERNICUS/S2') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start2, finish2) \
                            .sort('CLOUDY_PIXEL_PERCENTAGE', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for second time interval')        
                image2 = ee.Image(collection.first()).clip(rect).select('B2','B3','B4','B8') 
                timestamp2 = ee.Date(image2.get('system:time_start')).getInfo()
                timestamp2 = time.gmtime(int(timestamp2['value'])/1000)
                timestamp2 = time.strftime('%c', timestamp2) 
                systemid2 = image2.get('system:id').getInfo()  
                cloudcover2 = image2.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()               
            elif platform=='landsat8':
                collection = ee.ImageCollection('LANDSAT/LC08/C01/T1') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start1, finish1) \
                            .sort('CLOUD_COVER', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for first time interval')
                image1 = ee.Image(collection.first()).clip(rect).select('B2','B3','B4','B5','B6','B7')               
                timestamp1 = ee.Date(image1.get('system:time_start')).getInfo()
                timestamp1 = time.gmtime(int(timestamp1['value'])/1000)
                timestamp1 = time.strftime('%c', timestamp1) 
                systemid1 = image1.get('system:id').getInfo()
                cloudcover1 = image1.get('CLOUD_COVER').getInfo()
                collection = ee.ImageCollection('LANDSAT/LC08/C01/T1') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start2, finish2) \
                            .sort('CLOUD_COVER', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for second time interval')        
                image2 = ee.Image(collection.first()).clip(rect).select('B2','B3','B4','B5','B6','B7') 
                timestamp2 = ee.Date(image2.get('system:time_start')).getInfo()
                timestamp2 = time.gmtime(int(timestamp2['value'])/1000)
                timestamp2 = time.strftime('%c', timestamp2) 
                systemid2 = image2.get('system:id').getInfo()  
                cloudcover2 = image2.get('CLOUD_COVER').getInfo()                       
            elif platform=='landsat7':
                collection = ee.ImageCollection('LANDSAT/LE7') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start1, finish1) \
                            .sort('CLOUD_COVER', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for first time interval')        
                image1 = ee.Image(collection.first()).clip(rect).select('B1','B2','B3','B4','B5','B7')               
                timestamp1 = ee.Date(image1.get('system:time_start')).getInfo()
                timestamp1 = time.gmtime(int(timestamp1['value'])/1000)
                timestamp1 = time.strftime('%c', timestamp1) 
                systemid1 = image1.get('system:id').getInfo()
                cloudcover1 = image1.get('CLOUD_COVER').getInfo()
                collection = ee.ImageCollection('LANDSAT/LE7') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start2, finish2) \
                            .sort('CLOUD_COVER', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for second time interval')        
                image2 = ee.Image(collection.first()).clip(rect).select('B1','B2','B3','B4','B5','B7') 
                timestamp2 = ee.Date(image2.get('system:time_start')).getInfo()
                timestamp2 = time.gmtime(int(timestamp2['value'])/1000)
                timestamp2 = time.strftime('%c', timestamp2) 
                systemid2 = image2.get('system:id').getInfo()  
                cloudcover2 = image2.get('CLOUD_COVER').getInfo()   
            elif platform=='landsat5':
                collection = ee.ImageCollection('LT5_L1T') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start1, finish1) \
                            .sort('CLOUD_COVER', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for first time interval')        
                image1 = ee.Image(collection.first()).clip(rect).select('B1','B2','B3','B4','B5','B7')               
                timestamp1 = ee.Date(image1.get('system:time_start')).getInfo()
                timestamp1 = time.gmtime(int(timestamp1['value'])/1000)
                timestamp1 = time.strftime('%c', timestamp1) 
                systemid1 = image1.get('system:id').getInfo()
                cloudcover1 = image1.get('CLOUD_COVER').getInfo()
                collection = ee.ImageCollection('LT5_L1T') \
                            .filterBounds(ulPoint) \
                            .filterBounds(lrPoint) \
                            .filterDate(start2, finish2) \
                            .sort('CLOUD_COVER', True) 
                count = collection.toList(100).length().getInfo()    
                if count==0:
                    raise ValueError('No images found for second time interval')        
                image2 = ee.Image(collection.first()).clip(rect).select('B1','B2','B3','B4','B5','B7') 
                timestamp2 = ee.Date(image2.get('system:time_start')).getInfo()
                timestamp2 = time.gmtime(int(timestamp2['value'])/1000)
                timestamp2 = time.strftime('%c', timestamp2) 
                systemid2 = image2.get('system:id').getInfo()  
                cloudcover2 = image2.get('CLOUD_COVER').getInfo()   
#          register
            image2 = image2.register(image1,60)                                                               
#          iMAD
            chi2 = image1.select(0).multiply(0)
            allrhos = [ee.List.repeat(0,image1.bandNames().length())]
            inputlist = ee.List.sequence(1,niter)
            first = ee.Dictionary({'done':ee.Number(0),
                                   'image':image1.addBands(image2),
                                   'allrhos':allrhos,
                                   'chi2':ee.Image.constant(0),
                                   'MAD':ee.Image.constant(0)})
            
            print 'Iteration started ...'
            result = ee.Dictionary(inputlist.iterate(imad,first))
#          iteration emulation for debugging             
#            result = iterate(image1,image2,niter,first)

#          output result
            nbands = image1.bandNames().length().getInfo()
            bnames = ['MAD'+str(i+1) for i in range(nbands)]
            MAD = ee.Image(result.get('MAD')).rename(bnames)
            chi2 = ee.Image(result.get('chi2')).rename(['chi2'])
            allrhos = ee.Array(result.get('allrhos')).toList()              
            MAD = ee.Image.cat(MAD,chi2,image1,image2)
            if assexport == 'assexport':
#              export allrhos as CSV to Drive  
                hint = '(batch export to should complete)'             
                gdrhosexport = ee.batch.Export.table. \
                     toDrive(ee.FeatureCollection(allrhos.map(makefeature)),
                             description='driveExportTask', 
                             folder = 'EarthEngineImages',
                             fileNamePrefix=assexportname.replace('/','-') )
                gdrhosexportid = str(gdrhosexport.id)
                print '****Exporting correlations as CSV to Drive, task id: %s '%gdrhosexportid            
                gdrhosexport.start()                  
#              export to Assets 
                assexport = ee.batch.Export.image.toAsset(MAD,
                                                          description='assetExportTask', 
                                                          assetId=assexportname,scale=assexportscale,maxPixels=1e9)
                assexportid = str(assexport.id)
                print '****Exporting MAD image to Assets, task id: %s '%assexportid
                assexport.start() 
            else:
                assexportid = 'none'                
            if gdexport == 'gdexport':              
#              export to Drive 
                hint = '(batch export to should complete)'
                gdexport = ee.batch.Export.image.toDrive(MAD,
                                                         description='driveExportTask', 
                                                         folder = 'EarthEngineImages',
                                                         fileNamePrefix=gdexportname,scale=gdexportscale,maxPixels=1e9)
                gdexportid = str(gdexport.id)
                print '****Exporting MAD image to Google Drive, task id: %s '%gdexportid
                gdexport.start() 
            else:
                gdexportid = 'none'    
                
            glbls['minLat'] = minLat
            glbls['minLon'] = minLon
            glbls['maxLat'] = maxLat
            glbls['maxLon'] = maxLon  
            glbls['centerLon'] = centerLon
            glbls['centerLat'] = centerLat                  
                
            for rhos in allrhos.getInfo():
                print rhos               
            mapid = chi2.getMapId({'min': 0, 'max':10000, 'opacity': 0.7})                             
            return render_template('madout.html',
                                    title = 'Chi Square Image',
                                    mapid = mapid['mapid'], 
                                    token = mapid['token'], 
                                    gdexportid = gdexportid,
                                    assexportid = assexportid,
                                    centerLon = centerLon,
                                    centerLat = centerLat,
                                    systemid1 = systemid1,
                                    systemid2 = systemid2,
                                    cloudcover1 = cloudcover1,
                                    cloudcover2 = cloudcover2,
                                    timestamp1 = timestamp1,
                                    timestamp2 = timestamp2)  
        except Exception as e:
            if isinstance(e,ValueError):
                return 'Error in MAD: %s'%e
            else:
                return render_template('madout.html',
                                        title = 'Error in MAD: %s '%e + hint,
                                        gdexportid = 'none',
                                        assexportid = 'none',
                                        centerLon = centerLon,
                                        centerLat = centerLat,
                                        systemid1 = systemid1,
                                        systemid2 = systemid2,
                                        cloudcover1 = cloudcover1,
                                        cloudcover2 = cloudcover2,
                                        timestamp1 = timestamp1,
                                        timestamp2 = timestamp2)                 

@app.route('/omnibus.html', methods = ['GET', 'POST'])
def Omnibus():       
    global glbls, msg, local, zoom
    if request.method == 'GET':
        return render_template(omnibus1, msg = msg,
                                        minLat = glbls['minLat'],
                                        minLon = glbls['minLon'],
                                        maxLat = glbls['maxLat'],
                                        maxLon = glbls['maxLon'],
                                        centerLon = glbls['centerLon'],
                                        centerLat = glbls['centerLat'],
                                        zoom = zoom)
    else:
        try: 
            hint = '(enable export to bypass)' 
            startdate = request.form['startdate']  
            enddate = request.form['enddate']  
            orbitpass = request.form['pass']
            display = request.form['display']
            polarization1 = request.form['polarization']
            relativeorbitnumber = request.form['relativeorbitnumber']
            if polarization1 == 'VV,VH':
                polarization = ['VV','VH']
            else:
                polarization = polarization1
            significance = float(request.form['significance'])                         
            minLat = float(request.form['minLat'])
            minLon = float(request.form['minLon'])
            maxLat = float(request.form['maxLat'])
            maxLon = float(request.form['maxLon'])        
            if request.form.has_key('assexport'):        
                assexportscale = float(request.form['assexportscale'])
                assexportname = request.form['assexportname']
                assexport = request.form['assexport']
            else:
                assexport = 'none'
            if request.form.has_key('gdexport'):  
                gdexportscale = float(request.form['gdexportscale'])  
                gdexportname = request.form['gdexportname']    
                gdexport = request.form['gdexport']
            else:
                gdexport = 'none'   
            if request.form.has_key('median'):        
                median = True
            else:
                median = False                
            start = ee.Date(startdate)
            finish = ee.Date(enddate)            
            rect = ee.Geometry.Rectangle(minLon,minLat,maxLon,maxLat)     
            centerLon = (minLon + maxLon)/2.0
            centerLat = (minLat + maxLat)/2.0 
            ulPoint = ee.Geometry.Point([minLon,maxLat])   
            lrPoint = ee.Geometry.Point([maxLon,minLat])                
            collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
                        .filterBounds(ulPoint) \
                        .filterBounds(lrPoint) \
                        .filterDate(start, finish) \
                        .filter(ee.Filter.eq('transmitterReceiverPolarisation', polarization)) \
                        .filter(ee.Filter.eq('resolution_meters', 10)) \
                        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
                        .filter(ee.Filter.eq('orbitProperties_pass', orbitpass)) 
            if relativeorbitnumber != '':
                collection = collection.filter(ee.Filter.eq('relativeOrbitNumber_start', int(relativeorbitnumber))) 
            collection = collection.sort('system:time_start')                                     
            acquisition_times = ee.List(collection.aggregate_array('system:time_start')).getInfo()                                           
            count = len(acquisition_times) 
            if count<2:
                raise ValueError('Less than 2 images found')   
            timestamplist = []
            for timestamp in acquisition_times:
                tmp = time.gmtime(int(timestamp)/1000)
                timestamplist.append(time.strftime('%x', tmp))  
#          make timestamps in TYYYYMMDD format            
            timestamplist = [x.replace('/','') for x in timestamplist]  
            timestamplist = ['T20'+x[4:]+x[0:4] for x in timestamplist]
#          in case of duplicates add running integer
            timestamplist = [timestamplist[i] + '_' + str(i+1) for i in range(len(timestamplist))]
#          remove duplicates
            timestamps = str(timestamplist)
            timestamp = timestamplist[0]                   
            relativeorbitnumbers = str(ee.List(collection.aggregate_array('relativeOrbitNumber_start')).getInfo())                                                                      
            image = ee.Image(collection.first())                       
            systemid = image.get('system:id').getInfo()   
            projection = image.select(0).projection().getInfo()['crs']
#          make into collection of VV, VH or VVVH images and restore linear scale             
            if polarization1 == 'VV':
                pcollection = collection.map(get_vv)
            elif polarization1 == 'VH':
                pcollection = collection.map(get_vh)
            elif polarization1 == 'VV,VH':
                pcollection = collection.map(get_vvvh)
            elif polarization1 == 'HH':
                pcollection = collection.map(get_hh)
            elif polarization1 == 'HV':
                pcollection = collection.map(get_hv)
            elif polarization1 == 'HH,HV':
                pcollection = collection.map(get_hhhv)                      
#          get the list of images and clip to roi
            pList = pcollection.toList(count)   
            first = ee.Dictionary({'imlist':ee.List([]),'rect':rect}) 
            imList = ee.Dictionary(pList.iterate(clipList,first)).get('imlist')  
#          run the algorithm            
            result = ee.Dictionary(omnibus(imList,significance,median))
            cmap = ee.Image(result.get('cmap')).byte()   
            smap = ee.Image(result.get('smap')).byte()
            fmap = ee.Image(result.get('fmap')).byte()  
            bmap = ee.Image(result.get('bmap')).byte()
            cmaps = ee.Image.cat(cmap,smap,fmap,bmap).rename(['cmap','smap','fmap']+timestamplist[1:])  
            downloadpath = cmaps.getDownloadUrl({'scale':10})                  
            if assexport == 'assexport':
#              export to Assets 
                hint = '(batch export to should complete)'
                assexport = ee.batch.Export.image.toAsset(cmaps,
                                                          description='assetExportTask', 
                                                          assetId=assexportname,scale=assexportscale,maxPixels=1e9)
                assexportid = str(assexport.id)
                print '****Exporting to Assets, task id: %s '%assexportid
                assexport.start() 
            else:
                assexportid = 'none'                
            if gdexport == 'gdexport':
#              export to Drive 
                hint = '(batch export to should complete)'
                gdexport = ee.batch.Export.image.toDrive(cmaps,
                                                         description='driveExportTask', 
                                                         folder = 'EarthEngineImages',
                                                         fileNamePrefix=gdexportname,scale=gdexportscale,maxPixels=1e9)
                gdexportid = str(gdexport.id)
                print '****Exporting to Google Drive, task id: %s '%gdexportid
                gdexport.start() 
            else:
                gdexportid = 'none'    
 
            if display=='fmap':                                                                                  
                mapid = fmap.getMapId({'min': 0, 'max': count/2,'palette': jet, 'opacity': 0.4}) 
                title = 'Sequential omnibus frequency map'
            elif display=='smap':
                mapid = smap.getMapId({'min': 0, 'max': count,'palette': jet, 'opacity': 0.4}) 
                title = 'Sequential omnibus first change map'
            else:
                mapid = cmap.getMapId({'min': 0, 'max': count,'palette': jet, 'opacity': 0.4})   
                title = 'Sequential omnibus last change map'    
                
            glbls['minLat'] = minLat
            glbls['minLon'] = minLon
            glbls['maxLat'] = maxLat
            glbls['maxLon'] = maxLon  
            glbls['centerLon'] = centerLon
            glbls['centerLat'] = centerLat                                                 
                
            return render_template('omnibusout.html',
                                    mapid = mapid['mapid'], 
                                    token = mapid['token'], 
                                    title = title,
                                    centerLon = centerLon,
                                    centerLat = centerLat,
                                    zoom = zoom,
                                    projection = projection,
                                    systemid = systemid,
                                    count = count,
                                    downloadpath = downloadpath,
                                    timestamp = timestamp,
                                    assexportid = assexportid,
                                    gdexportid = gdexportid,
                                    timestamps = timestamps,
                                    polarization = polarization1,
                                    relativeorbitnumbers = relativeorbitnumbers)                                          
        except Exception as e:
            if isinstance(e,ValueError):
                return 'Error in MAD: %s'%e
            else:
                return render_template('omnibusout.html', 
                                        title = 'Error in omnibus: %s '%e + hint,
                                        centerLon = centerLon,
                                        centerLat = centerLat,
                                        zoom = zoom,
                                        projection = projection,
                                        systemid = systemid,
                                        count = count,
                                        timestamp = timestamp,
                                        timestamps = timestamps,
                                        polarization = polarization1,
                                        relativeorbitnumbers = relativeorbitnumbers)  
                                               
if __name__ == '__main__':   
    app.run(debug=True, host='0.0.0.0')
  