pipeline {
agent any
parameters {
    string(name: "AM_BRANCH", defaultValue: 'stable/1.9.x')
    string(name: "AM_VERSION", defaultValue: "1.9")
    string(name: "SS_BRANCH", defaultValue: "stable/0.14.x")
    string(name: "DEPLOYPUB_BRANCH", defaultValue: "dev/jenkins-vagrant-updates")
    string(name: "AMAUAT_BRANCH", defaultValue: "dev/issue-XXX-update-amauat-for-1.9")
    string(name: "DISPLAY", defaultValue: ":50")
    string(name: "WEBDRIVER", defaultValue: "Firefox")
    string(name: "ACCEPTANCE_TAGS", defaultValue: "mo-aip-reingest")
    booleanParam(name: "VAGRANT_PROVISION", defaultValue: "true")
    string(name: "OS_IMAGE", defaultValue: "Ubuntu 18.04")
    booleanParam(name: "DESTROY_VM", defaultValue: "false")
}

stages {
  
    stage('Get code') {
    steps {
      // Set build name
      script {
      currentBuild.displayName = "#${BUILD_NUMBER} AM:${AM_BRANCH} SS:${SS_BRANCH}"
      currentBuild.description = "OS: Ubuntu 18.04 <br>Tests: ${ACCEPTANCE_TAGS} from ${AMAUAT_BRANCH}"
      }

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
    }

    stage ('Create vm') {
    steps {
      sh '''
        echo Building Archivematica $AM_BRANCH and Storage Service $SS_BRANCH
        cd deploy-pub/playbooks/archivematica-bionic
        source ~/.secrets/openrc.sh
        if ! [ -f ${WORKSPACE}/.host ]
        then
         vagrant up --no-provision
         cat ~/.ssh/authorized_keys | vagrant ssh -c "cat >> .ssh/authorized_keys"
        fi

        if $VAGRANT_PROVISION; then
          rm -rf roles/
          echo 'strategy_plugins = ~/venvs/mitogen-0.2.7/ansible_mitogen/plugins/strategy' >> ansible.cfg
          echo 'strategy = mitogen_linear' >> ansible.cfg
          ansible-galaxy install -f -p roles -r requirements.yml
          export ANSIBLE_ARGS="-e archivematica_src_am_version=${AM_BRANCH} \
                                archivematica_src_ss_version=${SS_BRANCH} \
                                archivematica_src_configure_am_api_key="HERE_GOES_THE_AM_API_KEY" \
                                archivematica_src_configure_ss_api_key="HERE_GOES_THE_SS_API_KEY" \
                                archivematica_src_reset_am_all=True \
                                archivematica_src_reset_ss_db=True"
          vagrant provision
          vagrant ssh -c "sudo adduser ubuntu archivematica"
          vagrant ssh-config | tee >( grep HostName  | awk '{print $2}' > $WORKSPACE/.host) \
                                 >( grep "User " | awk '{print $2}' > $WORKSPACE/.user ) \
                                 >( grep IdentityFile | awk '{print $2}' > $WORKSPACE/.key )
        fi
        

     
      '''
     

    }
    
    }

    stage('Configure acceptance tests') {
    steps {
      git branch: env.AMAUAT_BRANCH, poll: false, url: 'https://github.com/artefactual-labs/archivematica-acceptance-tests'

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
    }

    stage('Run tests') {
    steps {
      sh '''
        export KEY=$(cat ${WORKSPACE}/.key)
        export SERVER=$(cat ${WORKSPACE}/.host)
        export SERVERUSER=$(cat ${WORKSPACE}/.user)
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
            -D home=${SERVERUSER} \
            -D server_user=${SERVERUSER} \
            -D transfer_source_path=${SERVERUSER}/archivematica-sampledata/TestTransfers/acceptance-tests \
            -D ssh_identity_file=${KEY} \
            --junit --junit-directory=results/ -v \
            -f=json -o=results/output-$i.json \
            --no-skipped || true

          env/bin/python -m behave2cucumber  -i results/output-$i.json -o results/cucumber-$i.json || true
        done
      '''
    }
    }

    stage('Archive results') {
    steps {
      junit allowEmptyResults: false, keepLongStdio: true, testResults: 'results/*.xml'
      cucumber 'results/cucumber-*.json'
    }
    }

  
  
}
    post {
        always {
      sh '''
        # Kill vnc server
        VNCPID=$(ps aux | grep Xtig[h] | grep ${DISPLAY} | awk '{print $2}')
        if [ "x$VNCPID" != "x" ]; then
          kill $VNCPID
        fi
        # Remove vm
        if $DESTROY_VM; then
          rm -f ${WORKSPACE}/.host
          rm -f ${WORKSPACE}/.key
          rm -f ${WORKSPACE}/.user
          cd deploy-pub/playbooks/archivematica-bionic/
          source ~/.secrets/openrc.sh
          vagrant destroy
       
        fi
      '''
        }
    }

}
