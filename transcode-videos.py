#!/usr/bin/python3

# Copyright 2018 Juan Orti Alcaine <j.orti.alcaine@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import sys
import os
import argparse
import subprocess
import logging


def transcode_video(video):
    supported_video_codec = True
    supported_audio_codec = True
    for stream in video.info['streams']:
        if stream['codec_type'] == "video" and \
                        stream['codec_name'] in args.unsupported_video_codecs:
            logging.warning("{v}: Unsupported video codec: {c}".format(v=video.filename, c=stream['codec_name']))
            supported_video_codec = False
        if not (not (stream['codec_type'] == "audio") or not (stream['codec_name'] in args.unsupported_audio_codecs)):
            logging.warning("{v}: Unsupported audio codec: {c}".format(v=video.filename, c=stream['codec_name']))
            supported_audio_codec = False
    if not supported_video_codec or not supported_audio_codec:
        logging.info("{}: Transcoding...".format(video.filename))
        target = os.path.join(video.directory, video.basename + "." + args.container)
        original_dir = os.path.join(video.directory, ".original")
        original_file = os.path.join(original_dir, video.filename)
        if os.path.exists(original_file):
            logging.info("{f} exists, cancelling transcoding.".format(f=original_file))
            return
        if not os.path.exists(original_dir):
            os.makedirs(original_dir)
        os.rename(video.path, original_file)
        if os.path.isfile(target):
            logging.info("{}: Skipping already converted video file".format(video.filename))
            return
        # ffmpeg -i file -nostats -loglevel 0 -c:v libx264 -preset slow -acodec copy -scodec copy h264-file
        command = ["ffmpeg", "-i", original_file, "-nostats", "-loglevel", "0"]
        if not supported_video_codec:
            command += ["-c:v", args.vcodec, "-preset", "slow"]
        else:
            command += ["-vcodec", "copy"]
        if not supported_audio_codec:
            command += ["-c:a", args.audio_codec]
        else:
            command += ["-acodec", "copy"]
        command += ["-scodec", "copy", target]
        logging.debug("Running command {}".format(command))
        try:
            retval = subprocess.call(command)
            logging.info("{}: Transcoded successfully".format(video.filename))
        except subprocess.CalledProcessError as ex:
            logging.error("{}: failed to transcode".format(video.filename))
            logging.error(ex)
            return
        except FileNotFoundError:
            logging.critical("Command ffmpeg not found.")
            sys.exit(1)
        if retval != 0:
            logging.error("{v}: ffmpeg return value {r}".format(v=video.filename, r=retval))
            if os.path.isfile(target):
                os.remove(target)
            return
    else:
        logging.info("{}: No transcoding needed.".format(video.filename))


def is_supported_video_file(file):
    supported_extensions = frozenset(['.mkv', '.mp4', '.avi', '.mpg', '.mpeg', '.divx'])
    if os.path.isfile(file):
        (basename, ext) = os.path.splitext(file)
        if ext in supported_extensions:
            return True
    return False


def search_videos(directory, files):
    """Scan a directory for supported video files"""
    if not directory and not files:
        raise ValueError("A directory or a file must be specified")
    if directory:
        for root, dirs, files in os.walk(directory):
            for name in files:
                if os.path.basename(root) == ".original":
                    continue
                f = os.path.join(root, name)
                if is_supported_video_file(f):
                    yield f
    if files:
        for f in files:
            if is_supported_video_file(f):
                yield f

parser = argparse.ArgumentParser(
    description='Script to prepare video files: download subtitles, transcode to supported formats, etc.')
parser.add_argument("-d", "--directory",
                    help="Directory to scan recursively for videos")
parser.add_argument("-c", "--container",
                    help="Target video container (default: mkv)",
                    default="mkv")
parser.add_argument("-vc", "--vcodec",
                    help="Target video codec (default: libx264)",
                    default="libx264")
parser.add_argument("-ac", "--audio-codec",
                    help="Target audio codec (default: ac3)",
                    default="ac3")
parser.add_argument("-uv", "--unsupported-video-codecs",
                    help="Unsupported video codecs (default: hevc)",
                    nargs='+',
                    default=[])
parser.add_argument("-ua", "--unsupported-audio-codecs",
                    help="Unsupported audio codecs (default: dts, dca)",
                    nargs='+',
                    default=[])
parser.add_argument("--log-level", default="INFO", help="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
parser.add_argument("file", nargs='*', help="Files to analyze")
args = parser.parse_args()
logging.basicConfig(level=args.log_level.upper())
for v in search_videos(directory=args.directory, files=args.file):
    logging.info("{}: Processing video".format(v))
    transcode_video(v)
