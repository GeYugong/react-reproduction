"""Serve pinned author WebShop on loopback using the frozen full catalog."""
from webshop_runtime import initialize

author, manifest = initialize()


@author.app.route('/_reproduction_health')
def health():
    return {'status':'ready','products':manifest['products'], 'goals':manifest['goals'],
            'goals_sha256':manifest['goals_sha256'], 'database_sha256':manifest['database_sha256']}


if __name__ == '__main__':
    author.app.run(host='127.0.0.1', port=3000, threaded=False, use_reloader=False)
