node {
  timestamps {
    stage('Get code') {
      // If environment variables are defined, honour them
      env.AM_BRANCH = sh(script: 'echo ${AM_BRANCH:-"stable/1.7.x"}', returnStdout: true).trim()
      env.AM_VERSION = sh(script: 'echo ${AM_VERSION:-"1.7"}', returnStdout: true).trim()
      env.SS_BRANCH = sh(script: 'echo ${SS_BRANCH:-"stable/0.12.x"}', returnStdout: true).trim()
      env.DEPLOYPUB_BRANCH = sh(script: 'echo ${DEPLOYPUB_BRANCH:-"master"}', returnStdout: true).trim()
      env.DISPLAY = sh(script: 'echo ${DISPLAY:-:50}', returnStdout: true).trim()
      env.WEBDRIVER = sh(script: 'echo ${WEBDRIVER:-"Firefox"}', returnStdout: true).trim()
      env.ACCEPTANCE_TAGS = sh(script: 'echo ${ACCEPTANCE_TAGS:-"uuids-dirs mo-aip-reingest icc tpc picc aip-encrypt-mirror"}', returnStdout: true).trim()
      env.VAGRANT_PROVISION = sh(script: 'echo ${VAGRANT_PROVISION:-"true"}', returnStdout: true).trim()
      env.VAGRANT_VAGRANTFILE = sh(script: 'echo ${VAGRANT_VAGRANTFILE:-Vagrantfile.openstack}', returnStdout: true).trim()
      env.OS_IMAGE = sh(script: 'echo ${OS_IMAGE:-"Ubuntu 16.04"}', returnStdout: true).trim()
      env.DESTROY_VM = sh(script: 'echo ${DESTROY_VM:-"true"}', returnStdout: true).trim()
      // Set build name
      currentBuild.displayName = "#${BUILD_NUMBER} AM:${AM_BRANCH} SS:${SS_BRANCH}"
      currentBuild.description = "OS: Ubuntu 16.04 DEB <br>Tests: ${ACCEPTANCE_TAGS}"

      git branch: env.AM_BRANCH, poll: false,
        url: 'https://github.com/artefactual/archivematica'
      git branch: env.SS_BRANCH, poll: false,
        url: 'https://github.com/artefactual/archivematica-storage-service'

      checkout([$class: 'GitSCM',
        branches: [[name: env.DEPLOYPUB_BRANCH]],
        doGenerateSubmoduleConfigurations: false,
        extensions:
          [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'deploy-pub']],
          submoduleCfg: [],
          userRemoteConfigs: [[url: 'https://github.com/artefactual/deploy-pub']]])

    }

    stage ('Create vm') {
      sh '''
        echo Building Archivematica and Storage Service using RPM packages
        cd deploy-pub/playbooks/archivematica-xenial-packages
        source ~/.secrets/openrc.sh
        vagrant up --no-provision

        if $VAGRANT_PROVISION; then
          vagrant provision
          vagrant ssh -c "sudo adduser ubuntu archivematica"
          vagrant ssh -c "git clone https://github.com/artefactual/archivematica-sampledata"
          vagrant ssh -c 'sudo -u archivematica bash -c " \
                          set -a -e -x
                          source /etc/default/archivematica-dashboard
                          cd /usr/share/archivematica/dashboard
                          /usr/share/archivematica/virtualenvs/archivematica-dashboard/bin/python manage.py install \
                             --username="admin" \
                             --password="archivematica" \
                             --email="archivematica@example.com" \
                             --org-name="Archivematica" \
                             --org-id="AM" \
                             --api-key="THIS_IS_THE_AM_APIKEY" \
                             --ss-url=http://\$(curl -s ifconfig.me):8000 \
                             --ss-user="admin" \
                             --ss-api-key="THIS_IS_THE_SS_APIKEY"
                              ";
                           '

        fi
        vagrant ssh-config | tee >( grep HostName  | awk '{print $2}' > $WORKSPACE/.host) \
                                 >( grep User | awk '{print $2}' > $WORKSPACE/.user ) \
                                 >( grep IdentityFile | awk '{print $2}' > $WORKSPACE/.key )

      '''

      env.SERVER = sh(script: "cat .host", returnStdout: true).trim()
      env.USER = sh(script: "cat .user", returnStdout: true).trim()
      env.KEY = sh(script: "cat .key", returnStdout: true).trim()
    }

    stage('Configure acceptance tests') {
      git branch: 'master', url: 'https://github.com/artefactual-labs/archivematica-acceptance-tests'
        properties([disableConcurrentBuilds(),
        gitLabConnection(''),
        [$class: 'RebuildSettings',
        autoRebuild: false,
        rebuildDisabled: false]])

      sh '''
        virtualenv -p python3 env
        env/bin/pip install -r requirements.txt
        env/bin/pip install behave2cucumber
        # Launch vnc server
        VNCPID=$(ps aux | grep Xtig[h] | grep ${DISPLAY} | awk '{print $2}')
        if [ "x$VNCPID" == "x" ]; then
          tightvncserver -geometry 1920x1080 ${DISPLAY}
        fi

        mkdir -p results/
        rm -rf results/*
      '''
    }

    stage('Run tests') {
      sh '''
        echo "Running $ACCEPTANCE_TAGS"
        for i in $ACCEPTANCE_TAGS; do
          case "$i" in
            premis-events) TIMEOUT=60m;;
            ipc) TIMEOUT=60m;;
            aip-encrypt) TIMEOUT=45m;;
            *) TIMEOUT=15m;;
          esac
          timeout $TIMEOUT env/bin/behave \
            --tags=$i \
            --no-skipped \
            -D am_version=${AM_VERSION} \
            -D driver_name=${WEBDRIVER} \
            -D am_username=admin \
            -D am_password=archivematica \
            -D am_url=http://${SERVER}:80/ \
            -D ss_username=admin \
            -D ss_password=artefactual \
            -D ss_api_key="THIS_IS_THE_SS_APIKEY" \
            -D ss_url=http://${SERVER}:8000/ \
            -D home=${USER} \
            -D server_user=${USER} \
            -D transfer_source_path=${USER}/archivematica-sampledata/TestTransfers/acceptance-tests \
            -D ssh_identity_file=${KEY} \
            -D pid_web_service_endpoint=${PID_WEB_SERVICE_ENDPOINT} \
            -D pid_web_service_key=${PID_WEB_SERVICE_KEY} \
            -D handle_resolver_url=${HANDLE_RESOLVER} \
            -D base_resolve_url=${BASE_RESOLVER_URL} \
            -D pid_xml_namespace=${PID_XML_NAMESPACE} \
            --junit --junit-directory=results/ -v \
            -f=json -o=results/output-$i.json \
            --no-skipped || true

          env/bin/python -m behave2cucumber  -i results/output-$i.json -o results/cucumber-$i.json || true
        done
      '''
    }

    stage('Archive results') {
      junit allowEmptyResults: false, keepLongStdio: true, testResults: 'results/*.xml'
      cucumber 'results/cucumber-*.json'
    }

    stage('Cleanup') {
      sh '''
        # Kill vnc server
        VNCPID=$(ps aux | grep Xtig[h] | grep ${DISPLAY} | awk '{print $2}')
        if [ "x$VNCPID" != "x" ]; then
          kill $VNCPID
        fi
        # Remove vm
        if $DESTROY_VM; then
          cd deploy-pub/playbooks/archivematica-xenial-packages/
          source ~/.secrets/openrc.sh
          vagrant destroy
        fi
      '''
    }
  }
}
