#!/usr/bin/env python

from collections import namedtuple
import math
import time

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
import cairo

import sailsd

Keys = namedtuple('Keys', '''up down left right esc ctrl ctrl_right f11 space backtick''')
KEYS = Keys(65362, 65364, 65361, 65363, 65307, 65507, 65508, 65480, 32, 96)


class Canvas(object):
    def __init__(self, context):
        self.context = context

    def __enter__(self):
        self.context.save()

    def __exit__(self, *args):
        self.context.restore()


class Wind(object):
    def __init__(self):
        self.x = 0
        self.y = 0


class SimWindow(Gtk.Window):
    def __init__(self, boat):
        self.boat = boat
        self.fps = 60
        GLib.timeout_add(1000.0/self.fps, self.update_boat)

        Gtk.Window.__init__(self, title='sails-ui')
        self.set_default_size(1000, 500)

        draw = Gtk.DrawingArea()
        draw.connect('draw', self.on_draw)
        self.add(draw)

        self.connect('scroll-event', self.on_scroll)
        self.connect('key-press-event', self.on_key)
        self.connect('key-release-event', self.on_key_release)
        self.set_events(self.get_events() |
                        Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK)

        self.ctrl_pressed = False
        self.is_fullscreen = False
        self.tracking_boat = True
        self.show_debug = True

        self.scale = 1
        self.translation_x, self.translation_y = 0, 0
        self.grid_width = 10000
        self.grid_spacing = 100
        self.grid_n = self.grid_width / self.grid_spacing

        self.color_background   = (0.75, 0.87, 0.95, 1)
        self.color_gridline     = (0.3,  0.3,  0.3,  1)
        self.color_text         = (0,    0,    0,    1)
        self.color_text_debug   = (1,    1,    1,    1)
        self.color_debug_pane   = (0,    0,    0,    0.8)
        self.color_boat_fill    = (1,    0.41, 0.28, 1)
        self.color_boat_stroke  = (0.32, 0.06, 0,   1)
        self.font = ('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        self.font_debug = ('Monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)

    def repaint(self):
        self.queue_draw()

    @property
    def scroll_amount(self):
        return 10 * 1/self.scale

    def on_scroll(self, widget, event):
        if self.ctrl_pressed:
            if event.direction == Gdk.ScrollDirection.UP:
                self.scale += self.scale/8
            elif event.direction == Gdk.ScrollDirection.DOWN:
                self.scale -= self.scale/8

            # smooth scrolling, broken on NixOS for some reason
            self.scale -= event.delta_y * (self.scale/8)

            if self.scale < 0.1:
                self.scale = 0.1
        else:
            scroll_factor = 1
            if event.direction == Gdk.ScrollDirection.UP:
                self.translation_y += scroll_factor * self.scroll_amount
            elif event.direction == Gdk.ScrollDirection.DOWN:
                self.translation_y -= scroll_factor * self.scroll_amount
            elif event.direction == Gdk.ScrollDirection.LEFT:
                self.translation_x += scroll_factor * self.scroll_amount
            elif event.direction == Gdk.ScrollDirection.RIGHT:
                self.translation_x -= scroll_factor * self.scroll_amount

            # smooth scrolling, broken on NixOS for some reason
            self.translation_x += event.delta_x * self.scroll_amount
            self.translation_y += event.delta_y * self.scroll_amount

        self.repaint()

    def on_key(self, widget, event):
        k = event.keyval

        if k == KEYS.up:
            self.translation_y += self.scroll_amount
        elif k == KEYS.down:
            self.translation_y -= self.scroll_amount
        elif k == KEYS.left:
            self.translation_x += self.scroll_amount
        elif k == KEYS.right:
            self.translation_x -= self.scroll_amount

        elif event.keyval == KEYS.ctrl or event.keyval == KEYS.ctrl_right:
            self.ctrl_pressed = True

        elif k == KEYS.esc:
            Gtk.main_quit()

        elif k == KEYS.f11:
            self.is_fullscreen = not self.is_fullscreen
            if self.is_fullscreen:
                self.fullscreen()
            else:
                self.unfullscreen()

        elif k == KEYS.space:
            self.tracking_boat = not self.tracking_boat
            self.translation_x = -self.boat.x * self.grid_spacing
            self.translation_y =  self.boat.y * self.grid_spacing

        elif k == KEYS.backtick:
            self.show_debug = not self.show_debug

        else:
            print(k)

        self.repaint()

    def on_key_release(self, widget, event):
        if event.keyval == KEYS.ctrl or event.keyval == KEYS.ctrl_right:
            self.ctrl_pressed = False

    def draw_debug_pane(self, cr):
        w, h = self.get_size()

        fields = (
                   'latitude',
                   'longitude',
                   'heading',
                   'sail_angle',
                   'rudder_angle'
                 )

        with Canvas(cr):
            cr.identity_matrix()
            cr.rectangle(0, 0, 200, h)
            cr.set_source_rgba(*self.color_debug_pane)
            cr.fill()

            cr.set_source_rgba(*self.color_text_debug)
            cr.select_font_face(*self.font_debug)

            cr.set_font_size(45)
            cr.move_to(5, 50)
            cr.show_text('sails')

            cr.set_font_size(11)

            cr.move_to(5, 75)
            cr.show_text(' status: {}'.format(self.boat.status))

            for i, field in enumerate(fields):
                cr.move_to(5, 75 + 15*i + 15)
                cr.show_text(' {name}: {data:0.2f}'.format(
                             name=field,
                             data=getattr(self.boat, field)))

    def draw_x_line(self, cr, n):
        x = n * 100
        with Canvas(cr):
            cr.set_source_rgba(*self.color_text)
            cr.select_font_face(*self.font)
            cr.set_font_size(10)
            cr.move_to(x + 10, -10)
            cr.show_text(str(n))

    def draw_x_gridline(self, cr, n):
        x = n * self.grid_spacing
        with Canvas(cr):
            cr.set_line_width(1)
            cr.move_to(x + 0.5, -self.grid_width)
            cr.line_to(x + 0.5, self.grid_width)
            cr.set_source_rgba(*self.color_gridline)
            cr.stroke()

    def draw_y_gridline(self, cr, n):
        y = n * self.grid_spacing
        with Canvas(cr):
            cr.set_line_width(1)
            cr.move_to(-self.grid_width, y + 0.5)
            cr.line_to(self.grid_width, y + 0.5)
            cr.set_source_rgba(*self.color_gridline)
            cr.stroke()

    def draw_boat(self, cr):
        points = (
                     (0, 0),
                     (0, 150),
                     (50, 200),
                     (100, 150),
                     (100, 0)
                 )
        width = max([i for i, _ in points])
        height = max([i for _, i in points])

        with Canvas(cr):
            cr.translate(self.boat.x * self.grid_spacing, -self.boat.y * self.grid_spacing)
            cr.rotate(self.boat.heading-(math.pi))
            cr.translate(-width/2, -height/2)

            cr.set_source_rgba(*self.color_boat_fill)

            cr.move_to(*points[0])
            for x, y in points:
                cr.line_to(x, y)
            cr.close_path()

            cr.fill_preserve()

            cr.set_source_rgba(*self.color_boat_stroke)
            cr.set_line_width(7)
            cr.set_line_join(cairo.LINE_JOIN_BEVEL)
            cr.stroke()

            self.draw_rudder(cr)

    def draw_rudder(self, cr):
        rudder_length = 35
        rudder_width = 7
        with Canvas(cr):
            cr.translate(50, 0)
            cr.rotate(self.boat.rudder_angle+math.pi)
            cr.move_to(0, 0)
            cr.line_to(0, rudder_length)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.stroke()

    def on_draw(self, widget, cr):
        w, h = self.get_size()
        if self.tracking_boat:
            cr.translate((w/2) - self.boat.x * self.grid_spacing * self.scale,
                         (h/2) + self.boat.y * self.grid_spacing * self.scale)
        else:
            cr.translate((w/2) + self.translation_x * self.scale,
                         (h/2) + self.translation_y * self.scale)
        cr.scale(self.scale, self.scale)

        cr.set_source_rgba(*self.color_background)
        cr.paint()

        for i in range(-self.grid_n, self.grid_n):
            self.draw_x_gridline(cr, i)
            self.draw_y_gridline(cr, i)
            self.draw_x_line(cr, i)
        self.draw_boat(cr)

        cr.set_source_rgba(*self.color_text)
        cr.select_font_face(*self.font)
        cr.set_font_size(20)
        cr.move_to(10, 40)
        cr.show_text('hello')

        cr.set_line_width(1)
        cr.move_to(-(self.grid_width + 0.5), 0.5)
        cr.line_to(self.grid_width + 0.5, 0.5)
        cr.move_to(0.5, -(self.grid_width + 0.5))
        cr.line_to(0.5, self.grid_width + 0.5)
        cr.stroke()

        if self.show_debug:
            self.draw_debug_pane(cr)

    def update_boat(self):
        self.boat.update()
        self.repaint()
        return True


if __name__ == '__main__':
    import signal
    import os
    import json

    boat = sailsd.Boat()

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    win = SimWindow(boat)
    win.connect('delete-event', Gtk.main_quit)
    win.show_all()

    #GLib.timeout_add(50, lambda: boat.update())
    Gtk.main()
