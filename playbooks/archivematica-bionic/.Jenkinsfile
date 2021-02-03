node {
  timestamps {
    stage('Get code') {
      // If environment variables are defined, honour them
      env.AM_BRANCH = sh(script: 'echo ${AM_BRANCH:-"stable/1.12.x"}', returnStdout: true).trim()
      env.AM_VERSION = sh(script: 'echo ${AM_VERSION:-"1.12"}', returnStdout: true).trim()
      env.SS_BRANCH = sh(script: 'echo ${SS_BRANCH:-"stable/0.17.x"}', returnStdout: true).trim()
      env.DEPLOYPUB_BRANCH = sh(script: 'echo ${DEPLOYPUB_BRANCH:-"master"}', returnStdout: true).trim()
      env.AMAUAT_BRANCH = sh(script: 'echo ${AMAUAT_BRANCH:-"master"}', returnStdout: true).trim()
      env.DISPLAY = sh(script: 'echo ${DISPLAY:-:50}', returnStdout: true).trim()
      env.WEBDRIVER = sh(script: 'echo ${WEBDRIVER:-"Firefox"}', returnStdout: true).trim()
      env.ACCEPTANCE_TAGS = sh(script: 'echo ${ACCEPTANCE_TAGS:-"uuids-dirs mo-aip-reingest icc tpc picc aip-encrypt-mirror"}', returnStdout: true).trim()
      env.VAGRANT_PROVISION = sh(script: 'echo ${VAGRANT_PROVISION:-"true"}', returnStdout: true).trim()
      env.VAGRANT_VAGRANTFILE = sh(script: 'echo ${VAGRANT_VAGRANTFILE:-Vagrantfile.openstack}', returnStdout: true).trim()
      env.OS_IMAGE = sh(script: 'echo ${OS_IMAGE:-"Ubuntu 18.04"}', returnStdout: true).trim()
      env.DESTROY_VM = sh(script: 'echo ${DESTROY_VM:-"true"}', returnStdout: true).trim()
      // Set build name
      currentBuild.displayName = "#${BUILD_NUMBER} AM:${AM_BRANCH} SS:${SS_BRANCH}"
      currentBuild.description = "OS: Ubuntu 18.04 <br>Tests: ${ACCEPTANCE_TAGS}"

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
        echo Building Archivematica $AM_BRANCH and Storage Service $SS_BRANCH
        cd deploy-pub/playbooks/archivematica-bionic
        source ~/.secrets/openrc.sh
        rm -rf roles/
        ansible-galaxy install -f -p roles -r requirements.yml
        export ANSIBLE_ARGS="-e archivematica_src_am_version=${AM_BRANCH} \
                                archivematica_src_ss_version=${SS_BRANCH} \
                                archivematica_src_configure_am_api_key="HERE_GOES_THE_AM_API_KEY" \
                                archivematica_src_configure_ss_api_key="HERE_GOES_THE_SS_API_KEY" \
                                archivematica_src_reset_am_all=True \
                                archivematica_src_reset_ss_db=True"
        vagrant up --no-provision
        cat ~/.ssh/authorized_keys | vagrant ssh -c "cat >> .ssh/authorized_keys"

        if $VAGRANT_PROVISION; then
          vagrant provision
          vagrant ssh -c "sudo adduser ubuntu archivematica"
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
      git branch: env.AMAUAT_BRANCH, url: 'https://github.com/artefactual-labs/archivematica-acceptance-tests'
        properties([disableConcurrentBuilds(),
        gitLabConnection(''),
        [$class: 'RebuildSettings',
        autoRebuild: false,
        rebuildDisabled: false],
        pipelineTriggers([pollSCM('*/5 * * * *')])])


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
            -D am_url=http://${SERVER}/ \
            -D ss_username=admin \
            -D ss_password=archivematica \
            -D ss_api_key="HERE_GOES_THE_SS_API_KEY" \
            -D ss_url=http://${SERVER}:8000/ \
            -D home=${USER} \
            -D server_user=${USER} \
            -D transfer_source_path=${USER}/archivematica-sampledata/TestTransfers/acceptance-tests \
            -D ssh_identity_file=${KEY} \
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
          cd deploy-pub/playbooks/archivematica-bionic/
          source ~/.secrets/openrc.sh
          vagrant destroy
        fi
      '''
    }
  }
}
