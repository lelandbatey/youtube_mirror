from __future__ import unicode_literals

import youtube_dl
import flask

import urllib.parse
import os.path
import hashlib
import time
import json
import sys

import threading
import logging


def concurrent(f):
    """Concurrent is a decorator for a function which will cause that function
    to immediately return when called, but be left running in 'in the
    background'. It is intended as a functional equivelent to the 'go func()'
    syntax in the Go programming language."""

    def err_logger(*args, **kwargs):
        '''
        err_logger logs uncaught exceptions, which is nice to have in long
        running processes in other threads.
        '''
        try:
            f(*args, **kwargs)
        except Exception as e:
            logging.error(e, exc_info=True)

    def rv(*args, **kwargs):
        t = threading.Thread(target=err_logger, args=(args), kwargs=kwargs)
        t.daemon = True
        t.start()
        return rv

    return rv


def human_readable_size(size, decimal_places=1):
    '''Takes a number of bytes and returns a string representing the "human
    version" of that file size.'''
    for unit in ['', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            break
        size /= 1024.0
    numfmt = '{{:.{}f}} {{}}'.format(decimal_places)
    return numfmt.format(size, unit)


class date_handler(json.JSONEncoder):
    """Handles printing of datetime objects in json.dumps."""

    def default(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif hasattr(obj, '__json__'):
            return obj.__json__()
        else:
            return json.JSONEncoder.default(self, obj)


def json_dump(indata):
    """Creates prettified json representation of passed in object."""
    return json.dumps(indata, sort_keys=True, indent=4, \
        separators=(',', ': '), cls=date_handler)


def jp(indata):
    """Prints json representation of object"""
    print(json_dump(indata))


class LoggerHook(object):
    def debug(self, _):
        pass

    def warning(self, _):
        pass

    def error(self, msg):
        print(msg)


### Stuff for downloading the video asynchronously via threads ###
DL_LOCATION = "./static/"
DL_STATUSES = dict()


def make_vidupdater(url):
    '''Returns a function to act as a status hook to YDL that updates the
    global DL_STATUS of that video with new info. When the video is totally
    downloaded, it's status is removed from DL_STATUSES.'''

    def update_status(data):
        global DL_STATUSES
        DL_STATUSES[url] = data
        if data['status'] == 'finished':
            del DL_STATUSES[url]

    return update_status


@concurrent
def download_video(url):
    global DL_STATUSES
    global DL_LOCATION
    DL_STATUSES[url] = dict()
    output_loc = "{}%(title)s__%(id)s.%(ext)s".format(DL_LOCATION)
    ydl_opts = {
        'logger': LoggerHook(),
        'progress_hooks': [make_vidupdater(url)],
        'format': 'bestvideo+bestaudio/best[ext=mp5]',
        "outtmpl": output_loc
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        print("Beginning the video download")
        try:
            ydl.download([url])
        except Exception as e:
            del DL_STATUSES[url]
            raise e


def list_videos():
    '''Returns a list of all .mp4 files in the current folder, sorted by date
    since that file was modified.'''
    global DL_LOCATION
    videos = [
        os.path.join(DL_LOCATION, path) for path in os.listdir(DL_LOCATION)
        if path.endswith('.mp4') or path.endswith('.mkv')
    ]
    videos = sorted(videos, key=os.path.getctime)[::-1]
    return videos


APP = flask.Flask(__name__)


def generate_video_table():
    vids = list_videos()
    rows = []
    base = '''
        <table>
            <thead>
                <tr>
                    <th>Downloaded videos</th>
                    <th>File size</th>
                </tr>
            </thead>
            <tbody>
                {}
            </tbody>
        </table>'''
    for v in vids:
        basename = '<td><a href="{}">{}</a></td>'.format(
            urllib.parse.quote(v), os.path.basename(v))
        filesize = '<td>{}</td>'.format(
            human_readable_size(os.path.getsize(v)))
        deletebutton = '<td filename="{}"><i class="material-icons" style="color: crimson;">delete_forever</i></td>'
        deletebutton = deletebutton.format(v)
        rows.append('<tr>{}</tr>'.format('\n'.join(
            [basename, filesize, deletebutton])))
    return base.format("\n".join(rows))


@APP.route('/')
def root():
    return flask.render_template(
        'frontpage.html', vidlinks=generate_video_table())


@APP.route('/api/current_downloads')
def view_statuses():
    global DL_STATUSES
    testdat = {
        "https://www.youtube.com/watch?v=NzHkMcUErgE": {
            "_eta_str": "00:57",
            "_percent_str": " 13.9%",
            "_speed_str": " 6.04MiB/s",
            "_total_bytes_str": "404.31MiB",
            "downloaded_bytes": 58719232,
            "elapsed": 9.275935649871826,
            "eta": 57,
            "filename": "./static/Dice Friends \u2014 Escape from Semolo Plateau Ep2.mp4",
            "speed": 6330275.911391362,
            "status": "downloading",
            "tmpfilename": "./static/Dice Friends \u2014 Escape from Semolo Plateau Ep2.mp4.part",
            "total_bytes": 423951827
        }
    }
    # return flask.jsonify(testdat)
    return flask.jsonify(DL_STATUSES)


@APP.route('/api/finished_downloads')
def view_vidlist():
    return flask.jsonify(list_videos())


@APP.route('/api/start_download', methods=['POST'])
def start_download():
    data = flask.request.get_json(force=True)
    url = data['url']
    if not url in DL_STATUSES:
        download_video(url)
    return ""


@APP.route('/api/video_table')
def view_vidtable():
    return generate_video_table()


@APP.route('/api/video', methods=['POST'])
def video_controller():
    data = flask.request.get_json(force=True)
    video = data['video']
    for v in list_videos():
        if video == v:
            os.remove(v)
    return ''


def main():
    if len(sys.argv) < 2:
        print("Launching flask service")
        APP.debug = True
        APP.run(host='0.0.0.0', port=5000)
        return
    download_video(sys.argv[1])
    while True:
        time.sleep(1)
        jp(DL_STATUSES)
        if not DL_STATUSES:
            break


if __name__ == '__main__':
    main()
