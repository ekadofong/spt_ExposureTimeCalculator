# -*- coding: utf-8 -*-

from __future__ import print_function, division

import sys
import os
from os import path
import numpy as np
import collections

from . import dm_utils

WAV_ERR_SHIFT = 3


def arm_name(arm_num):
    arm_num = np.array(arm_num)
    return np.where(arm_num == 0, 'b',
                    np.where(arm_num == 1, 'r',
                             np.where(arm_num == 2, 'n',
                                      'm')))


def arm_number(armStr):
    return dict(b=0, r=1, n=2, m=3)[armStr]


def calculateFiberMagnitude(wav, mag, filterName):
    """Calculate the average magnitude over the bandpass"""
    #                           50%/nm  50%/nm peak
    filterBandpasses = dict(g=(399.5,  546.5, 0.97),
                            r=(542.5,  696.5, 0.95),
                            i=(698.5,  853.3, 0.90),  # i2
                            z=(852.5,  932.0, 0.97),
                            y=(943.0, 1072.0, 0.95)
                            )
    wav0, wav1, peak = filterBandpasses[filterName]

    counts = np.exp(-mag)
    bandpass = np.where(np.logical_and(wav >= wav0, wav <= wav1), peak, 0)
    fiberMag = -np.log(np.trapz(bandpass * counts, wav) / np.trapz(bandpass, wav))
    return fiberMag


def write_ascii(aset, arms, asciiTable, outDir):
    """Write an ascii table"""

    outFile = os.path.join(outDir, asciiTable)
    nFiber = len(aset[0].flux)
    for i in range(nFiber):
        with open('%s.dat' % (outFile) if nFiber == 1 else '%s.%d.dat' % (outFile, i), "w") as fd:
            fd.write('''#  1  WAVELENGTH  [nm]
#  2  FLUX        [10^-17 erg/s/cm^2/A]
#  3  ERROR       [10^-17 erg/s/cm^2/A]
#  4  MASK        [1=masked]
#  5  SKY         [10^-17 erg/s/cm^2/A]
#  6  ARM         [0=blue,1=red,2=NIR,3=redMR]
'''
                     )

            for a, armStr in zip(aset, arms):
                lam = a.wavelength[i]
                flux = a.flux[i]
                sigma = np.sqrt(a.covar[i][0])
                mask = a.mask[i]
                sky = a.sky[i]
                armNum = arm_number(armStr)
                for j in range(len(lam)):
                    fd.write('%8.3f %12.4e %12.4e %2d %12.4e %1d\n' %
                             (lam[j], flux[j], sigma[j], mask[j], sky[j], armNum))


def strToBool(val):
    if isinstance(val, bool):
        return val
    if val.lower() in ("1", "t", "true"):
        return True
    elif val.lower() in ("0", "f", "false"):
        return False
    else:
        sys.exit("Unable to interpret \"%s\" as bool" % val)


class Pfsspec(object):

    def __init__(self):
        self.params = {'EXP_NUM': '8',
                       'MAG_FILE': '22.5',
                       'countsMin': '0.1',
                       'etcFile': 'out/ref.snc.dat',
                       'nrealize': '1',
                       'outDir': 'out',
                       'asciiTable': 'None',
                       'ra': 150.0,
                       'dec': 2.0,
                       'tract': 0,
                       'patch': '0,0',
                       'visit': 1,
                       'catId': 0,
                       'objId': 1,
                       'fiberId': 1,
                       'spectrograph': 1,
                       'pfsConfigFull': 'f',
                       'writeFits': 't',
                       'writePfsArm': 't',
                       'plotArmSet': 'f',
                       'plotObject': 'f',
                       'SKY_SUB_FLOOR': '0.01',
                       'SKY_SUB_MODE': 'random'
                       }
        return None

    def set_param(self, param_name, param_value):
        if param_name in self.params.keys():
            try:
                self.params[param_name] = param_value
            except:
                print('Error!')
        else:
            print('param_name %s can not be recognized ...' % (param_name))
        return 0

    def load_param_file(self, filename):
        try:
            for line in open(filename, 'r'):
                a = line.split()
                if line[0] != '#' and len(a) > 0:
                    self.params[a[0]] = a[1]
        except:
            sys.exit('Error: maybe file not found')
        return 0

    def make_sim_spec(self):
        self.outdir = self.params['outDir']
        self.tract = self.params['tract']
        self.patch = self.params['patch']
        self.visit = int(self.params['visit'])
        self.fiberId = self.params['fiberId']
        self.ra = self.params['ra']
        self.dec = self.params['dec']
        self.catId = self.params['catId']
        self.objId = self.params['objId']
        self.spectrograph = self.params['spectrograph']
        try:
            self.mag_file = '%.4e' % (float(self.params['MAG_FILE']))
        except:
            self.mag_file = self.params['MAG_FILE']
        ''' some checks '''
        self.writeFits = strToBool(self.params['writeFits'])
        self.writePfsArm = strToBool(self.params['writePfsArm'])
        self.plotArmSet = strToBool(self.params['plotArmSet'])
        self.plotObject = strToBool(self.params['plotObject'])
        self.asciiTable = self.params['asciiTable']
        self.pfsConfigFull = strToBool(self.params['pfsConfigFull'])
        self.sky_sub_err = float(self.params['SKY_SUB_FLOOR'])
        self.sky_sub_mode = self.params['SKY_SUB_MODE']
        nrealize = int(self.params['nrealize'])
        nexp = int(self.params['EXP_NUM'])
        try:
            if len(self.fiberId) > 0:
                self.multi_info = 1
            else:
                self.multi_info = 0
        except:
            self.multi_info = 0

        if not self.writeFits and not self.asciiTable:
            sys.exit("Please specify asciiTable or omit writeFits (or say writeFits true)")
        if not os.path.exists(self.outdir):
            try:
                os.makedirs(self.outdir)
            except OSError as e:
                sys.exit("Unable to create outDir: %s" % e)
        if nrealize <= 0:
            sys.exit("Please specify at least one realization")
        ''' check magfile '''
        if os.path.exists(self.mag_file):
            dat = np.loadtxt(self.mag_file)
            nobj = dat.shape[1] - 1
        else:
            nobj = 1
        if nobj > 1:
            if nrealize > 1:
                sys.exit("The number of realization should be one for multiple input template")
            else:
                if self.multi_info == 0:
                    objIds = np.arange(self.objId, self.objId + nobj)
                    tmp, catIds = self.catId, np.empty(nobj, dtype=np.int32)
                    catIds.fill(tmp)
                    fiberIds = np.arange(self.fiberId, self.fiberId + nobj)
                    tmp, ras = self.ra, np.empty(nobj, dtype=np.float32)
                    ras.fill(tmp)
                    tmp, decs = self.dec, np.empty(nobj, dtype=np.float32)
                    decs.fill(tmp)
                    tmp, tracts = self.tract, np.empty(nobj, dtype=np.int32)
                    tracts.fill(tmp)
                    tmp, patches = self.patch, np.empty(nobj, dtype='U3')
                    patches.fill(tmp)
                else:
                    objIds = np.array(self.objId)
                    catIds = np.array(self.catId)
                    fiberIds = np.array(self.fiberId)
                    ras = np.array(self.ra)
                    decs = np.array(self.dec)
                    tracts = np.array(self.tract)
                    patches = np.array(self.patch)
        else:
            if nrealize > 1:
                objIds = np.arange(self.objId, self.objId + nrealize)
                tmp, catIds = self.catId, np.empty(nrealize, dtype=np.int32)
                catIds.fill(tmp)
                fiberIds = range(self.fiberId, self.fiberId + nrealize)
                tmp, ras = self.ra, np.empty(nrealize, dtype=np.float32)
                ras.fill(tmp)
                tmp, decs = self.dec, np.empty(nrealize, dtype=np.float32)
                decs.fill(tmp)
                tmp, tracts = self.tract, np.empty(nrealize, dtype=np.int32)
                tracts.fill(tmp)
                tmp, patches = self.patch, np.empty(nrealize, dtype='U3')
                patches.fill(tmp)
            else:
                objIds = np.array([self.objId])
                catIds = np.array([self.catId])
                fiberIds = np.array([self.fiberId])
                ras = np.array([self.ra])
                decs = np.array([self.dec])
                tracts = np.array([self.tract])
                patches = np.array([self.patch])
        '''
            ## read input file ##
            # arm: 0-3 telling us which arm the data comes from (arm_name will convert to b, r, n, m)
            # wav: wavelength
            # nsv: per-pixel (instrumental + sky) variance (counts^2)
            # trn: conversion from I_nu to counts
            # smp: samplingFactor.  A fiddle factor for the Poisson noise in HgCdTe devices
            # skm: sky flux
        '''
        with open(self.params['etcFile'], 'r') as f:
            for line in f.readlines():
                if "EXP_NUM" in line:
                    nexp_etc = int(line.split()[2])
        arm, wav, nsv, trn, smp, skm = np.loadtxt(self.params['etcFile'], usecols=(0, 2, 5, 8, 9, 10), unpack=True)
        ''' remove sky systematics '''
        skm_sysref = skm.copy()
        skmp = np.roll(skm_sysref, 1)
        skmp[0] = 0.0
        skmm = np.roll(skm_sysref, -1)
        skmm[-1] = 0.0
        skm_sysref = np.amax([skm_sysref, skmm, skmp], axis=0)
        nsv_sys = (self.sky_sub_err * np.sqrt(nexp_etc) * skm_sysref)**2
        nsv_rnd = nsv - nsv_sys
        ''' '''
        arm = arm.astype(int)
        trn[trn < 1.0e26] = 1.0e26
        ''' load magnitude or filename '''
        if os.path.exists(self.mag_file):
            dat = np.loadtxt(self.mag_file)
            nobj = dat.shape[1] - 1
            _lam = dat[:, 0]
            mag = np.empty((len(wav), nobj))
            for i in range(nobj):
                _mag = dat[:, i + 1]
                mag[:, i] = np.interp(wav, _lam, _mag)
        else:
            nobj = 1
            mag = np.empty((len(wav), nobj))
            mag[:, 0].fill(self.mag_file)
        wav_mtrx = np.empty((len(wav), nobj))
        trn_mtrx = np.empty((len(wav), nobj))
        smp_mtrx = np.empty((len(wav), nobj))
        nsv_rnd_mtrx = np.empty((len(wav), nobj))
        nsv_sys_mtrx = np.empty((len(wav), nobj))
        for i in range(nobj):
            wav_mtrx[:, i] = wav
            trn_mtrx[:, i] = trn
            smp_mtrx[:, i] = smp
            nsv_rnd_mtrx[:, i] = nsv_rnd
            nsv_sys_mtrx[:, i] = nsv_sys * float(nexp) / float(nexp_etc)
        ''' calculate the flux etc. in observed units '''
        fnu = 10**(-0.4 * (mag + 48.6))
        flam = 3.0e18 * fnu / (10 * wav_mtrx)**2 / 1e-17
        counts = trn_mtrx * fnu
        if (counts == 0).any():
            print("counts == 0 detected in some pixels; setting to %g for variance" % (float(self.params['countsMin'])), file=sys.stderr)
            countsp = np.where(counts == 0, float(self.params['countsMin']), counts)  # version of counts with zero pixels replaced
        else:
            countsp = counts
        if self.sky_sub_mode == 'residual' or self.sky_sub_mode == 'residual2':
            snr1 = countsp / np.sqrt(smp_mtrx * countsp + nsv_rnd_mtrx) * np.sqrt(nexp)
            snr2 = countsp / np.sqrt(smp_mtrx * countsp + (nsv_rnd_mtrx + nsv_sys_mtrx)) * np.sqrt(nexp)
        else:
            snr1 = countsp / np.sqrt(smp_mtrx * countsp + (nsv_rnd_mtrx + nsv_sys_mtrx)) * np.sqrt(nexp)
            snr2 = countsp / np.sqrt(smp_mtrx * countsp + (nsv_rnd_mtrx + nsv_sys_mtrx)) * np.sqrt(nexp)
        sigma1 = flam / snr1
        sigma2 = flam / snr2

        msk = np.zeros_like(wav, dtype=np.int32)
        sky = 3.0e18 * (skm / trn) / (10 * wav)**2 / 1e-17
        skm_sysref = sky.copy()
        skmp = np.roll(skm_sysref, 1)
        skmp[0] = 0.0
        skmm = np.roll(skm_sysref, -1)
        skmm[-1] = 0.0
        skm_sysref = np.amax([skm_sysref, skmm, skmp], axis=0)
        arm = arm_name(arm)
        arms = np.array(sorted(set(arm), key=lambda x: dict(b=0, r=1, m=1.5, n=2)[x]))  # unique values of arm
        '''
            Create and populate the objects corresponding to the datamodel

            First the parameters describing the observation, in PfsDesign and PfsConfig
        '''
        objectMags = []
        if nobj > 1:
            for i in range(nobj):
                objectMags.append([calculateFiberMagnitude(wav, mag[:, i], b) for b in "grizy"])
        else:
            for i in range(nrealize):
                objectMags.append([calculateFiberMagnitude(wav, mag[:, 0], b) for b in "grizy"])

        pfsDesign = dm_utils.makePfsDesign(tracts, patches, fiberIds, ras, decs, catIds, objIds, objectMags)

        pfsConfig = dm_utils.makePfsConfig(pfsDesign.pfsDesignId, self.visit, tracts, patches, fiberIds, ras, decs, catIds, objIds, objectMags)

        '''
            Create the PfsArm;  we'll put each realisation into a different fibre
        '''
        metadata = {}
        mapper = {"NO_DATA": 1}
        flags = dm_utils.MaskHelper(**mapper)
        pfsArmSet = []
        for armStr in arms:
            thisArm = (arm == armStr)
            identity = {'visit': self.visit,
                        'pfsDesignId': pfsDesign.pfsDesignId,
                        'spectrograph': self.spectrograph,
                        'arm': arm_number(armStr)
                        }
            if self.sky_sub_mode == 'residual' or self.sky_sub_mode == 'residual2':
                sky_res_fac = np.random.normal(0.0, self.sky_sub_err)
            else:
                sky_res_fac = 0.0
            nPt = np.sum(thisArm)
            datalam = []
            dataflux = []
            datasky = []
            datamask = []
            datacovar = []
            if nobj > 1:
                for i in range(nobj):
                    datalam.append(wav[thisArm])
                    if self.sky_sub_mode == 'residual':
                        flux = []
                        for j in range(nexp):
                            skyres = skm_sysref[thisArm] * sky_res_fac
                            flux.append(flam[thisArm, i] + np.random.normal(0.0, sigma1[thisArm, i] * np.sqrt(nexp)) + skyres)
                        dataflux.append(np.nanmean(flux, axis=0))
                    elif self.sky_sub_mode == 'residual2':
                        flux = []
                        for j in range(nexp):
                            skyres = (skm_sysref[thisArm] - np.roll(skm_sysref[thisArm], WAV_ERR_SHIFT)) * sky_res_fac
                            flux.append(flam[thisArm, i] + np.random.normal(0.0, sigma1[thisArm, i] * np.sqrt(nexp)) + skyres)
                        dataflux.append(np.nanmean(flux, axis=0))
                    else:
                        dataflux.append(flam[thisArm, i] + np.random.normal(0.0, sigma1[thisArm, i]))
                    datasky.append(sky[thisArm])
                    datamask.append(msk[thisArm])
                    covar = np.zeros(3 * nPt).reshape((3, nPt))
                    covar[0] = sigma2[thisArm, i]**2
                    datacovar.append(covar)
            else:
                for i in range(nrealize):
                    datalam.append(wav[thisArm])
                    if self.sky_sub_mode == 'residual':
                        flux = []
                        for j in range(nexp):
                            skyres = skm_sysref[thisArm] * sky_res_fac
                            flux.append(flam[thisArm, 0] + np.random.normal(0.0, sigma1[thisArm, 0] * np.sqrt(nexp)) + skyres)
                        dataflux.append(np.nanmean(flux, axis=0))
                    elif self.sky_sub_mode == 'residual2':
                        flux = []
                        for j in range(nexp):
                            skyres = (skm_sysref[thisArm] - np.roll(skm_sysref[thisArm], WAV_ERR_SHIFT)) * sky_res_fac
                            flux.append(flam[thisArm, 0] + np.random.normal(0.0, sigma1[thisArm, 0] * np.sqrt(nexp)) + skyres)
                        dataflux.append(np.nanmean(flux, axis=0))
                    else:
                        dataflux.append(flam[thisArm, 0] + np.random.normal(0.0, sigma1[thisArm, 0]))
                    datasky.append(sky[thisArm])
                    datamask.append(msk[thisArm])
                    covar = np.zeros(3 * nPt).reshape((3, nPt))
                    covar[0] = sigma2[thisArm, 0]**2
                    datacovar.append(covar)
            pfsArm = dm_utils.PfsArm(identity=identity,
                                     fiberId=fiberIds,
                                     wavelength=np.array(datalam),
                                     flux=np.array(dataflux),
                                     mask=np.array(datamask),
                                     sky=np.array(datasky),
                                     covar=np.array(datacovar),
                                     flags=flags,
                                     metadata=metadata
                                     )
            pfsArmSet.append(pfsArm)
        if self.plotArmSet:
            for pfsArm in pfsArmSet:
                pfsArm.plot(fiberId=None, usePixels=False, ignorePixelMask=0x0, show=True)
        '''
            Time for I/O
        '''
        ''' Fits '''
        if self.writeFits:
            pfsDesign.write(self.outdir)         # pfsDesign file
            pfsConfig.write(self.outdir)         # pfsConfig file
            if self.writePfsArm:                 # write pfsArm files
                for pfsArm in pfsArmSet:
                    pfsArm.write(self.outdir)
        ''' Ascii '''
        if self.asciiTable != "None":
            write_ascii(pfsArmSet, arms, self.asciiTable, self.outdir)
            print("ASCII table %s was generated" % self.asciiTable)
        '''
            Now make the PfsObject from the PfsArmSet
        '''
        pfsObjects, pfsVisitHashes = dm_utils.makePfsObjects(pfsConfig=pfsConfig, visit0=self.visit, pfsArmSet=pfsArmSet,
                                                             minWavelength=350., maxWavelength=1260., dWavelength=0.08)
        for pfsObject, pfsVisitHash in zip(pfsObjects, pfsVisitHashes):
            if self.writeFits:
                pfsObject.write(self.outdir)         # pfsDesign file
            self.pfsVisitHash = pfsVisitHash
            if self.plotObject:
                pfsObject.plot(show=True)

        return 0
