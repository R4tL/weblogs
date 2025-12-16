import os
import time
import re
import crossfiledialog
from flask import Flask, render_template, Response, redirect, request
from pygtail import Pygtail

# NOTE This is still a WORK IN PROGRESS
# [x] adapt for Edge, firefox
# [ ] add a CLI
# [ ] manage color themes in a more convenient way
# [ ] comment
# [ ] separate README

weblogs = Flask(__name__)

config = weblogs.config
config.update(
    PROGRAM_NAME='MyProject',
    FILE_DISPLAY_PATH='static/example.log',
    FILE_FULL_PATH=os.path.abspath('static/example.log'),
    FONT_SIZE=10,
    REFRESH_RATE=1000,
    SMOOTHNESS=0.01,
    CONSOLE_THEME='Light',
    COLORIZE_LOGS=False,
    CONVERT_ANSI_COLORS=False,
    COLORIZE_NEXT_LINE=False,
    CURRENT_HTML_TAG=''
)

COLORS_PRESET = {
    'DEBUG': {'color': 0x808080, 'font-weight': 'normal', 'background-color': 'transparent', 'text-decoration': 'none'},
    'INFO': {'color': 0x0000FF, 'font-weight': 'normal', 'background-color': 'transparent', 'text-decoration': 'none'},
    'WARNING': {'color': 0xFF0000, 'font-weight': 'bold', 'background-color': 'transparent', 'text-decoration': 'none'},
    'ERROR': {'color': 0xFF0000, 'font-weight': 'normal', 'background-color': 'red', 'text-decoration': 'none'},
    'CRITICAL': {'color': 0xFF0000, 'font-weight': 'normal', 'background-color': 'red', 'text-decoration': 'underline'}
}

ANSI_TO_HTML = {
    'RESET': {'ansi': 0, 'color': 'initial', 'font-weight': 'normal', 'background-color': 'transparent', 'text-decoration': 'none'},
    'BOLD': {'ansi': 1, 'font-weight': 'bold'},
    'UNDERLINE': {'ansi': 4, 'text-decoration': 'underline'},
    'BLACK': {'ansi': 30, 'color': 0x000000},
    'RED': {'ansi': 31, 'color': 0xFF0000},
    'GREEN': {'ansi': 32, 'color': 0x00FF00},
    'YELLOW': {'ansi': 33, 'color': 0xFFFF00},
    'BLUE': {'ansi': 34, 'color': 0x0000FF},
    'MAGENTA': {'ansi': 35, 'color': 0xFF00FF},
    'CYAN': {'ansi': 36, 'color': 0x00FFFF},
    'WHITE': {'ansi': 37, 'color': 0xFFFFFF},
    'GRAY': {'ansi': 38, 'color': 0x808080},
    'BG_BLACK': {'ansi': 40, 'background-color': 'black'},
    'BG_RED': {'ansi': 41, 'background-color': 'red'},
    'BG_GREEN': {'ansi': 42, 'background-color': 'green'},
    'BG_YELLOW': {'ansi': 43, 'background-color': 'yellow'},
    'BG_BLUE': {'ansi': 44, 'background-color': 'blue'},
    'BG_MAGENTA': {'ansi': 45, 'background-color': 'magenta'},
    'BG_CYAN': {'ansi': 46, 'background-color': 'cyan'},
    'BG_WHITE': {'ansi': 47, 'background-color': 'white'},
    'BG_GRAY': {'ansi': 48, 'background-color': 'gray'},
}

def colorize(line):

    log_levels = [True if level in line else False for level in COLORS_PRESET.keys()]
    if True in log_levels:
        levelnum = log_levels.index(True)
        preset = list(COLORS_PRESET.values())[levelnum]
        config['CURRENT_HTML_TAG'] = '<span style="color: #{:06x}; font-weight:{}; background-color:{}; text-decoration:{};">'.format(
            preset['color'],
            preset['font-weight'],
            preset['background-color'],
            preset['text-decoration']
        )

    return config['CURRENT_HTML_TAG'] + line + '</span>'

def colorize_from_ansi(line):

    ansi_regex = re.compile(r'\[(?P<arg_1>\d+)(;(?P<arg_2>\d+)(;(?P<arg_3>\d+))?)?m')

    line = line.replace('\x1b', '')
    line = line.replace('[0m', '</span>')

    def convert(match):

        args = match.groupdict()

        preset = {'color': 'initial', 'font-weight': 'normal', 'background-color': 'transparent', 'text-decoration': 'none'}
        for arg_val in args.values():
            if arg_val:
                ansi_tag_dict = list(filter(lambda tag: tag['ansi'] == int(arg_val), ANSI_TO_HTML.values()))
                preset_attrs = list(ansi_tag_dict[0].items())[1:]
                for attr_name, attr_val in preset_attrs:
                    if attr_name in preset:
                        preset[attr_name] = attr_val

        config['CURRENT_HTML_TAG'] = '<span style="color: #{:06x}; font-weight:{}; background-color:{}; text-decoration:{};">'.format(
            preset['color'],
            preset['font-weight'],
            preset['background-color'],
            preset['text-decoration']
        )
        return config['CURRENT_HTML_TAG']

    line = ansi_regex.sub(convert, line)

    if config['COLORIZE_NEXT_LINE']:
        line = config['CURRENT_HTML_TAG'] + line

    if line.find('<span') >= 0 and line.find('</span>') == -1:
        config['COLORIZE_NEXT_LINE'] = True
    else:
        config['COLORIZE_NEXT_LINE'] = False

    return line

@weblogs.route("/", methods=["GET", "POST"])
def index():

    if request.method == "POST":

        print(request.form)
        # Uploading the configuration with the new parameters selected by the user from the .html page.
        for config_key, config_value in request.form.items():
            if config_value:
                match config_key:
                    case "refresh_rate":
                        config['REFRESH_RATE'] = int(config_value)
                    case "font_size":
                        config['FONT_SIZE'] = int(config_value)
                    case "smoothness":
                        config['SMOOTHNESS'] = float(config_value)
                    case "colors":
                        match config_value:
                            case 'auto':
                                config['COLORIZE_LOGS'] = True
                                config['CONVERT_ANSI_COLORS'] = False
                            case 'ansi':
                                config['COLORIZE_LOGS'] = False
                                config['CONVERT_ANSI_COLORS'] = True
                            case 'no_colors':
                                config['COLORIZE_LOGS'] = False
                                config['CONVERT_ANSI_COLORS'] = False
                    case "theme":
                        config['CONSOLE_THEME'] = config_value

    # Remove the log offset file each time the root url is refreshed
    offset_file_path = config['FILE_FULL_PATH'] + ".offset"
    if os.path.isfile(offset_file_path):
        os.remove(offset_file_path)

    return render_template(
        template_name_or_list='logs.html',
        program_name=config['PROGRAM_NAME'],
        file_path=config['FILE_DISPLAY_PATH'],
        font_size=config['FONT_SIZE'],
        refresh_rate=config['REFRESH_RATE'],
        smoothness=config['SMOOTHNESS'],
        console_theme=config['CONSOLE_THEME'].lower(),
        colorize_logs=config['COLORIZE_LOGS'],
        convert_ansi_colors=config['CONVERT_ANSI_COLORS']
    )

@weblogs.route('/uptime')
def uptime():

    def generate():
        x= 0
        while True:
            yield "data:" + str(x) + "\n\n"
            x += 1
            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')

@weblogs.route('/show_logs')
def show_logs():

    def generate():
        for line in Pygtail(config['FILE_FULL_PATH'], every_n=1, encoding= 'utf-8'):
            if config['COLORIZE_LOGS']:
                line = colorize(line)
            if config['CONVERT_ANSI_COLORS']:
                line = colorize_from_ansi(line)
            yield "retry:" + str(config['REFRESH_RATE']) + "\n" + "data:" + line + "\n\n"
            time.sleep(config['SMOOTHNESS'])

    return Response(generate(), mimetype= 'text/event-stream')

@weblogs.route("/open_file")
def open_file():

    path = crossfiledialog.open_file(
        title="Pick a new log file !",
        start_dir=os.path.dirname(os.getcwd()),
        filter=["*.log", "*.txt", "*.doc", "*.docx", "*.md", "*.rtf", "*.msg"]
    )
    # Updating the weblogs configuration with the relative path of the new selected file (only if there is one !)
    if path:
        config['FILE_FULL_PATH'] = path
        config['FILE_DISPLAY_PATH'] = os.path.relpath(path)

    return redirect("/")

@weblogs.route('/wsgi_env')
def show_wsgi_env():

    env= {}
    for varname, val in request.environ.items():
        env[varname] = str(val)

    return env

@weblogs.route('/flask_env')
def show_flask_env():
    env= {}
    for varname, val in config.items():
        env[varname] = str(val)

    return env


if __name__ == "__main__":
    weblogs.run(host= '127.0.0.1', port= 5000, debug=True)
