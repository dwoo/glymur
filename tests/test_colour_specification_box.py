# -*- coding:  utf-8 -*-
"""
Test suite specifically targeting ICC profiles
"""

# Standard library imports ...
from datetime import datetime
import os
import struct
import sys
import tempfile
import unittest
import warnings

# Third party library imports
import numpy as np
import pkg_resources as pkg

# Local imports
import glymur
from glymur import Jp2k
from glymur._iccprofile import _ICCProfile
from glymur.jp2box import (
    ColourSpecificationBox, ContiguousCodestreamBox, FileTypeBox,
    ImageHeaderBox, JP2HeaderBox, JPEG2000SignatureBox
)
from glymur.core import SRGB
from .fixtures import WINDOWS_TMP_FILE_MSG


class TestColourSpecificationBox(unittest.TestCase):
    """Test suite for colr box instantiation."""

    def setUp(self):
        self.j2kfile = glymur.data.goodstuff()

        j2k = Jp2k(self.j2kfile)
        codestream = j2k.get_codestream()
        height = codestream.segment[1].ysiz
        width = codestream.segment[1].xsiz
        num_components = len(codestream.segment[1].xrsiz)

        self.jp2b = JPEG2000SignatureBox()
        self.ftyp = FileTypeBox()
        self.jp2h = JP2HeaderBox()
        self.jp2c = ContiguousCodestreamBox()
        self.ihdr = ImageHeaderBox(height=height, width=width,
                                   num_components=num_components)

        relpath = os.path.join('data', 'sgray.icc')
        iccfile = pkg.resource_filename(__name__, relpath)
        with open(iccfile, mode='rb') as f:
            self.icc_profile = f.read()

    def test_bad_method_printing(self):
        """
        A bad method should not cause a printing failure.

        It's enough that it doesn't error out.
        """
        relpath = os.path.join('data', 'issue405.dat')
        filename = pkg.resource_filename(__name__, relpath)
        with open(filename, 'rb') as f:
            f.seek(8)
            with warnings.catch_warnings():
                # Lots of things wrong with this file.
                warnings.simplefilter('ignore')
                box = ColourSpecificationBox.parse(f, length=80, offset=0)
        str(box)

    @unittest.skipIf(sys.platform == 'win32', WINDOWS_TMP_FILE_MSG)
    def test_colr_with_out_enum_cspace(self):
        """must supply an enumerated colorspace when writing"""
        j2k = Jp2k(self.j2kfile)

        boxes = [self.jp2b, self.ftyp, self.jp2h, self.jp2c]
        boxes[2].box = [self.ihdr, ColourSpecificationBox(colorspace=None)]
        with tempfile.NamedTemporaryFile(suffix=".jp2") as tfile:
            with self.assertRaises(IOError):
                j2k.wrap(tfile.name, boxes=boxes)

    @unittest.skipIf(sys.platform == 'win32', WINDOWS_TMP_FILE_MSG)
    def test_missing_colr_box(self):
        """jp2h must have a colr box"""
        j2k = Jp2k(self.j2kfile)
        boxes = [self.jp2b, self.ftyp, self.jp2h, self.jp2c]
        boxes[2].box = [self.ihdr]
        with tempfile.NamedTemporaryFile(suffix=".jp2") as tfile:
            with self.assertRaises(IOError):
                j2k.wrap(tfile.name, boxes=boxes)

    @unittest.skipIf(sys.platform == 'win32', WINDOWS_TMP_FILE_MSG)
    def test_bad_approx_jp2_field(self):
        """JP2 has requirements for approx field"""
        j2k = Jp2k(self.j2kfile)
        boxes = [self.jp2b, self.ftyp, self.jp2h, self.jp2c]
        colr = ColourSpecificationBox(colorspace=SRGB, approximation=1)
        boxes[2].box = [self.ihdr, colr]
        with tempfile.NamedTemporaryFile(suffix=".jp2") as tfile:
            with self.assertRaises(IOError):
                j2k.wrap(tfile.name, boxes=boxes)

    def test_default_colr(self):
        """basic colr instantiation"""
        colr = ColourSpecificationBox(colorspace=SRGB)
        self.assertEqual(colr.method, glymur.core.ENUMERATED_COLORSPACE)
        self.assertEqual(colr.precedence, 0)
        self.assertEqual(colr.approximation, 0)
        self.assertEqual(colr.colorspace, SRGB)
        self.assertIsNone(colr.icc_profile)

    def test_icc_profile(self):
        """basic colr box with ICC profile"""
        colr = ColourSpecificationBox(icc_profile=self.icc_profile)
        self.assertEqual(colr.method, glymur.core.ENUMERATED_COLORSPACE)
        self.assertEqual(colr.precedence, 0)
        self.assertEqual(colr.approximation, 0)

        icc_profile = _ICCProfile(colr.icc_profile)
        self.assertEqual(icc_profile.header['Version'], '2.1.0')
        self.assertEqual(icc_profile.header['Color Space'], 'gray')
        self.assertIsNone(icc_profile.header['Datetime'])

        # Only True for version4
        self.assertFalse('Profile Id' in icc_profile.header.keys())

    def test_colr_with_bad_color(self):
        """colr must have a valid color, strange as though that may sound."""
        colorspace = -1
        approx = 0
        colr = ColourSpecificationBox(colorspace=colorspace,
                                      approximation=approx)
        with tempfile.TemporaryFile() as tfile:
            with self.assertRaises(IOError):
                colr.write(tfile)

    def test_write_colr_with_bad_method(self):
        """
        A colr box has an invalid method.

        Expect an IOError when trying to write to file.
        """
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            colr = ColourSpecificationBox(colorspace=SRGB, method=5)
        with tempfile.TemporaryFile() as tfile:
            with self.assertRaises(IOError):
                colr.write(tfile)


class TestSuite(unittest.TestCase):
    """Test suite for ICC Profile code."""

    def setUp(self):
        relpath = os.path.join('data', 'sgray.icc')
        iccfile = pkg.resource_filename(__name__, relpath)
        with open(iccfile, mode='rb') as f:
            self.buffer = f.read()

    def test_bad_rendering_intent(self):
        """
        The rendering intent is not in the range 0-4.

        It should be classified as 'unknown'
        """
        intent = struct.pack('>I', 10)
        self.buffer = self.buffer[:64] + intent + self.buffer[68:]

        icc_profile = _ICCProfile(self.buffer)
        self.assertEqual(icc_profile.header['Rendering Intent'], 'unknown')

    def test_version4(self):
        """
        ICC profile is version 4
        """
        leadoff = struct.pack('>IIBB', 416, 0, 4, 0)
        self.buffer = leadoff + self.buffer[10:]

        icc_profile = _ICCProfile(self.buffer)
        self.assertEqual(icc_profile.header['Version'], '4.0.0')
        self.assertTrue('Profile Id' in icc_profile.header.keys())

    def test_icc_profile(self):
        """
        Verify full ICC profile
        """
        relpath = os.path.join('data', 'text_GBR.jp2')
        jfile = pkg.resource_filename(__name__, relpath)
        with self.assertWarns(UserWarning):
            # The brand is wrong, this is JPX, not JP2.
            j = Jp2k(jfile)
        box = j.box[3].box[1]

        self.assertEqual(box.icc_profile_header['Size'], 1328)
        self.assertEqual(box.icc_profile_header['Color Space'], 'RGB')
        self.assertEqual(box.icc_profile_header['Connection Space'], 'XYZ')
        self.assertEqual(box.icc_profile_header['Datetime'],
                         datetime(2009, 2, 25, 11, 26, 11))
        self.assertEqual(box.icc_profile_header['File Signature'], 'acsp')
        self.assertEqual(box.icc_profile_header['Platform'], 'APPL')
        self.assertEqual(box.icc_profile_header['Flags'],
                         'not embedded, can be used independently')
        self.assertEqual(box.icc_profile_header['Device Manufacturer'], 'appl')
        self.assertEqual(box.icc_profile_header['Device Model'], '')
        self.assertEqual(box.icc_profile_header['Device Attributes'],
                         ('reflective, glossy, positive media polarity, '
                          'color media'))
        self.assertEqual(box.icc_profile_header['Rendering Intent'],
                         'perceptual')
        np.testing.assert_almost_equal(box.icc_profile_header['Illuminant'],
                                       np.array([0.9642023, 1.0, 0.824905]),
                                       decimal=6)
        self.assertEqual(box.icc_profile_header['Creator'], 'appl')
