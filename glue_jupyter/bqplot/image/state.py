import numpy as np

from echo import CallbackProperty, delay_callback
from glue.viewers.matplotlib.state import (DeferredDrawCallbackProperty as DDCProperty,
                                           DeferredDrawSelectionCallbackProperty as DDSCProperty)

from glue.viewers.image.state import ImageViewerState, ImageLayerState
from glue.core.state_objects import StateAttributeLimitsHelper
from glue.core.units import find_unit_choices, UnitConverter


class BqplotImageViewerState(ImageViewerState):
    image_external_padding = DDCProperty(0, docstring='How much padding to add to the '
                                                      'fixed resolution buffer beyond the '
                                                      'bounds of the image, as a value relative '
                                                      'to the axes width/height (0 means no '
                                                      'padding)')


class BqplotImageLayerState(ImageLayerState):
    c_min = DDCProperty(docstring='The lower level used for the contours')
    c_max = DDCProperty(docstring='The upper level used for the contours')
    c_display_unit = DDSCProperty(docstring='The units to use to display contour levels')
    level_mode = DDSCProperty(0, docstring='How to distribute the contour levels')
    n_levels = DDCProperty(5, docstring='The number of levels, in Linear mode')
    levels = CallbackProperty(docstring='List of values where to create the contour lines')
    labels = CallbackProperty(docstring='List of labels for each contour')
    contour_percentile = DDSCProperty(docstring='The percentile value used to '
                                                'automatically calculate levels for '
                                                'the contour')
    contour_colors = CallbackProperty(["red", "orange", "yellow", "green", "blue"])
    bitmap_visible = CallbackProperty(True, 'whether to show the image as a bitmap')
    contour_visible = CallbackProperty(False, 'whether to show the image as contours')

    def __init__(self, *args, **kwargs):
        super(BqplotImageLayerState, self).__init__(*args, **kwargs)

        BqplotImageLayerState.level_mode.set_choices(self, ['Linear', 'Custom'])
        percentile_display = {100: 'Min/Max',
                              99.5: '99.5%',
                              99: '99%',
                              95: '95%',
                              90: '90%',
                              'Custom': 'Custom'}

        BqplotImageLayerState.contour_percentile.set_choices(self, [100, 99.5, 99, 95, 90,
                                                                    'Custom'])
        BqplotImageLayerState.contour_percentile.set_display_func(self, percentile_display.get)
        self.contour_lim_helper = StateAttributeLimitsHelper(self, attribute='attribute',
                                                             percentile='contour_percentile',
                                                             lower='c_min', upper='c_max')

        def format_unit(unit):
            if unit is None:
                return 'Native units'
            else:
                return unit

        BqplotImageLayerState.c_display_unit.set_display_func(self, format_unit)

        self.add_callback('n_levels', self._update_levels)
        self.add_callback('c_min', self._update_levels)
        self.add_callback('c_max', self._update_levels)
        self.add_callback('level_mode', self._update_levels)
        self.add_callback('levels', self._update_labels)
        self.add_callback('attribute', self._update_c_display_unit_choices)
        self.add_callback('c_display_unit', self._convert_units_c_limits, echo_old=True)

        self._update_c_display_unit_choices()
        self._update_levels()

    def _update_priority(self, name):
        # if levels and level_mode get modified at the same time
        # make sure externally 'levels' is set first, so we then
        # can overwrite levels when we switch to Linear mode
        # this is tested in test_contour_state
        if name == 'levels':
            return 10
        return 0

    def _update_levels(self, ignore=None):
        if self.level_mode == "Linear":
            self.levels = np.linspace(self.c_min, self.c_max, self.n_levels).tolist()

    def _update_labels(self, ignore=None):
        # TODO: we may want to have ways to configure this in the future
        self.labels = ["{0:.4g}".format(level) for level in self.levels]

    def _update_c_display_unit_choices(self, *args):

        if self.layer is None:
            BqplotImageLayerState.c_display_unit.set_choices(self, [])
            return

        component = self.layer.get_component(self.attribute)
        if component.units:
            c_choices = find_unit_choices([(self.layer, self.attribute, component.units)])
        else:
            c_choices = ['']
        BqplotImageLayerState.c_display_unit.set_choices(self, c_choices)
        self.c_display_unit = component.units

    def _convert_units_c_limits(self, old_unit, new_unit):

        if (
            getattr(self, '_previous_attribute', None) is self.attribute and
            old_unit != new_unit and
            self.layer is not None
        ):

            limits = np.hstack([self.c_min, self.c_max, self.levels])

            converter = UnitConverter()

            limits_native = converter.to_native(self.layer,
                                                self.attribute, limits,
                                                old_unit)

            limits_new = converter.to_unit(self.layer,
                                           self.attribute, limits_native,
                                           new_unit)

            with delay_callback(self, 'c_min', 'c_max', 'levels'):
                self.c_min, self.c_max = sorted(limits_new[:2])
                self.levels = tuple(limits_new[2:])

        # Make sure that we keep track of what attribute the limits
        # are for - if the attribute changes, we should not try and
        # update the limits.
        self._previous_attribute = self.attribute
