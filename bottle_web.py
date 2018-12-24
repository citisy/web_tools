"""https://blog.csdn.net/happyteafriends/article/details/42552093"""


from bottle import route, run, static_file, request, post, get, abort
import json
import os


@get('/do_get')
def do_get():
    # data = request.query['data']  # default: ISO-8859-15 encoding
    data = request.query.data   # utf8 encoding
    return data


@post('/do_post')
def do_post():
    post_value = request.POST.decode('utf8')  # correct to print the chinese
    data = post_value.get('data')  # if post value is data type, use this
    # js = [i for i in post_value.keys()][0]  # if post value is json type, use this
    # data = json.loads(js)['data']
    return data


im_str = '''
<p><img src="{fn}" style="max-width: 50%"></img></p>
'''


@route('/<imgn>/<filename:re:.*\.png>')  # <filename> means all the file type
def img(imgn, filename):
    if not os.path.exists(imgn):      # unnecessary, 'cause the static_file would also raise 404 error
        return abort(404)
    return static_file(filename, root=imgn)


@route('/show_img')
def show_img():
    return im_str.format(fn='./img/show.png')


form_str = '''
<form action="/form_post" method="post">
    <center>
    <p><textarea name="text"  rows="8" cols="150" /></textarea></p>
    <input type="submit" value="submit" />
    </center>
</form>
'''


@route('/form_post')
def form():
    return form_str


@route('/form_post', method='POST')
def form_post():
    post_value = request.POST.decode('utf8')
    text = post_value.get('text')
    return form_str + '</br>this is your input text: ' + text


upload_str = '''
<form action="/upload" method="post" enctype="multipart/form-data">
    <input type="file" name="file" />
    <input type="submit" value="Upload" />
</form>
'''


@route('/upload')
def upload():
    return upload_str


@route('/upload', method='POST')
def do_upload():
    upload = request.files.get('file')
    # overwrite is false, when the file is exist, it will raise error
    upload.save('./img/%s' % upload.filename, overwrite=True)
    return upload_str


run(host='0.0.0.0', port=8080, server='wsgiref')
"""
about server:
    wsgiref: serial
    gunicorn: only unix, parallel
    paste: parallel
        attention: if use this framework in python3, u will rewrite the httpserver.py in line 309:
            self.wsgi_write_chunk('') -> self.wsgi_write_chunk(b'')
        so that when its status code is 304, it won't raise error
        and, it can't support chinese charset
"""