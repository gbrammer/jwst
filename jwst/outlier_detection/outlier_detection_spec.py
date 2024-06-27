"""Class definition for performing outlier detection on spectra."""
from stdatamodels.jwst import datamodels

from jwst.datamodels import ModelContainer

from ..resample import resample_spec, resample_utils
from .outlier_detection import OutlierDetection
from .utils import _remove_file, create_median, detect_outliers

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


__all__ = ["OutlierDetectionSpec"]


class OutlierDetectionSpec(OutlierDetection):
    """Class definition for performing outlier detection on spectra.

    This is the controlling routine for the outlier detection process.
    It loads and sets the various input data and parameters needed by
    the various functions and then controls the operation of this process
    through all the steps used for the detection.

    Notes
    -----
    This routine performs the following operations::

      1. Extracts parameter settings from input model and merges
         them with any user-provided values
      2. Resamples all input images into grouped observation mosaics.
      3. Creates a median image from all grouped observation mosaics.
      4. Blot median image to match each original input image.
      5. Perform statistical comparison between blotted image and original
         image to identify outliers.
      6. Updates input data model DQ arrays with mask of detected outliers.

    """
    def do_detection(self, input_models, **kwargs):
        """Flag outlier pixels in DQ of input images."""
        # TODO factor this out
        self._convert_inputs(**kwargs)

        save_intermediate_results = kwargs['save_intermediate_results']
        if kwargs['resample_data'] is True:
            # Start by creating resampled/mosaic images for
            #  each group of exposures
            resamp = resample_spec.ResampleSpecData(input_models, single=True,
                                                    blendheaders=False, **kwargs)
            drizzled_models = resamp.do_drizzle(input_models)
            if save_intermediate_results:
                for model in drizzled_models:
                    model.meta.filename = kwargs["make_output_path"](
                        basepath=model.meta.filename,
                        suffix="_outlier_s2d.fits",
                    )
                    log.info("Writing out resampled spectra...")
                    model.save(model.meta.filename)
        else:
            drizzled_models = input_models
            for i in range(len(input_models)):
                drizzled_models[i].wht = resample_utils.build_driz_weight(
                    input_models[i],
                    weight_type=kwargs['weight_type'],
                    good_bits=kwargs['good_bits'])

        # Initialize intermediate products used in the outlier detection
        median_model = datamodels.ImageModel(drizzled_models[0].data.shape)
        median_model.meta = drizzled_models[0].meta
        median_model.meta.filename = kwargs["make_output_path"](
            basepath=input_models[0].meta.filename,
            suffix='median'
        )

        # Perform median combination on set of drizzled mosaics
        # create_median should be called as a method from parent class
        median_model.data = create_median(drizzled_models, kwargs['maskpt'])

        if save_intermediate_results:
            log.info("Writing out MEDIAN image to: {}".format(
                     median_model.meta.filename))
            median_model.save(median_model.meta.filename)
        else:
            # since we're not saving intermediate results if the drizzled models
            # were written to disk, remove them
            if not kwargs['in_memory']:
                for fn in drizzled_models._models:
                    _remove_file(fn)
                    log.info(f"Removing file {fn}")

        # Perform outlier detection using statistical comparisons between
        # each original input image and its blotted version of the median image
        detect_outliers(
            input_models,
            median_model,
            kwargs["snr"],
            kwargs["scale"],
            kwargs["backg"],
            kwargs["resample_data"],
        )

        del median_model
