from fabric.api import task, env, local

@task(alias='w')
def do_it_all():
    """Extract data from weddslist. Grab all the data"""
    local('set __CLI_TOOL_WRAPPER=weddslist; python cli.py weddslist -g')


