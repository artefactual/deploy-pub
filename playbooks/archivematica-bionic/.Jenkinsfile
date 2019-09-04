pipeline {
agent any
parameters {
    string(name: "AM_BRANCH", defaultValue: 'qa/1.x')
    string(name: "AM_VERSION", defaultValue: "1.9")
    string(name: "SS_BRANCH", defaultValue: "qa/0.x")
    string(name: "DEPLOYPUB_BRANCH", defaultValue: "dev/jenkins-vagrant-updates")
    string(name: "AMAUAT_BRANCH", defaultValue: "dev/issue-722-test-using-microservices-task-endpoints")
    string(name: "DISPLAY", defaultValue: ":50")
    string(name: "WEBDRIVER", defaultValue: "Firefox")
    string(name: "ACCEPTANCE_TAGS", defaultValue: "black-box")
    booleanParam(name: "VAGRANT_PROVISION", defaultValue: "true")
    string(name: "OS_IMAGE", defaultValue: "ubuntu1804")
    booleanParam(name: "DESTROY_VM", defaultValue: "false")
}

stages {
  
    stage('Get code') {
    steps {
      // Set build name
      script {
      currentBuild.displayName = "#${BUILD_NUMBER} AM:${AM_BRANCH} SS:${SS_BRANCH}"
      currentBuild.description = "OS: ${OS_IMAGE} <br>Tests: ${ACCEPTANCE_TAGS} from ${AMAUAT_BRANCH}"
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
        script {
        def cloudvm = openstackMachine cloud: 'Artefactual CI', template: env.OS_IMAGE
        echo cloudvm.getAddress() 
        writeFile file: 'hostip', text: cloudvm.getAddress()
        env.CLOUDVM = cloudvm.getAddress() 
        env.CLOUDUSER = 'ubuntu'
        }
        
      sh '''
        echo Building Archivematica $AM_BRANCH and Storage Service $SS_BRANCH on ${CLOUDVM}
        
        
        # Wait for the vm to be available
        while ! ssh -o ConnectTimeout=2 ubuntu@${CLOUDVM}
        do 
           sleep 1
        done
        # Give some time for unnatended upgrades start, and wait for it
        sleep 600s
       ssh ubuntu@${CLOUDVM} "while sudo fuser /var/{lib/{dpkg,apt/lists},cache/apt/archives}/lock >/dev/null 2>&1; do
            sleep 1; done"
        # Install minimum requirements
        ssh ubuntu@${CLOUDVM} "sudo apt-get update; sudo apt-get install -y python-minimal"
       '''
      }
    }
    
    stage('Deploy vm'){
    steps {
    sh '''
        if $VAGRANT_PROVISION; then
          cd deploy-pub/playbooks/archivematica-bionic
          rm -rf roles/
          #echo 'strategy_plugins = ~/venvs/mitogen-0.2.7/ansible_mitogen/plugins/strategy' >> ansible.cfg
          #echo 'strategy = mitogen_linear' >> ansible.cfg
          ansible-galaxy install -f -p roles -r requirements-qa.yml
          echo "am-local   ansible_user=${CLOUDUSER} ansible_host=${CLOUDVM}" > inventory
          cat inventory
          export ANSIBLE_HOST_KEY_CHECKING=False
          ansible-playbook -i inventory  \
          -e ansible_user=ubuntu \
          -e archivematica_src_install_devtools=False \
          -e archivematica_src_am_version=${AM_BRANCH} \
          -e archivematica_src_ss_version=${SS_BRANCH} \
          -e archivematica_src_configure_am_api_key="HERE_GOES_THE_AM_API_KEY" \
          -e archivematica_src_configure_ss_api_key="HERE_GOES_THE_SS_API_KEY" \
          -e archivematica_src_reset_am_all=True \
          -e archivematica_src_reset_ss_db=True \
          singlenode.yml
          
          ssh ubuntu@${CLOUDVM} "sudo adduser ubuntu archivematica"
          ssh ubuntu@${CLOUDVM} "sudo ln -sf /home/ubuntu /home/archivematica"
          ssh ubuntu@${CLOUDVM} "sudo ln -sf /home/ubuntu/archivematica-sampledata /home/"
           
        fi
        

     
      '''
     

    }
    
    }

    stage('Run tests') {
    steps {
        git branch: env.AMAUAT_BRANCH, poll: false, url: 'https://github.com/artefactual-labs/archivematica-acceptance-tests'

      sh '''
        rm -rf env
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
            -D am_url=http://${CLOUDVM}/ \
            -D am_api_key="HERE_GOES_THE_AM_API_KEY" \
            -D ss_username=admin \
            -D ss_password=archivematica \
            -D ss_api_key="HERE_GOES_THE_SS_API_KEY" \
            -D ss_url=http://${CLOUDVM}:8000/ \
            -D home=${CLOUDUSER} \
            -D server_user=${CLOUDUSER} \
            -D transfer_source_path=/home/${CLOUDUSER}/archivematica-sampledata/TestTransfers/acceptance-tests \
            -D ssh_identity_file=~/.ssh/id_rsa \
            --junit --junit-directory=results/ -v \
            -f=json -o=results/output-$i.json \
            --no-skipped || true

          env/bin/python -m behave2cucumber  -i results/output-$i.json -o results/cucumber-$i.json || true
        done
      '''
      
      sh '''
        # Kill vnc server
        VNCPID=$(ps aux | grep Xtig[h] | grep ${DISPLAY} | awk '{print $2}')
        if [ "x$VNCPID" != "x" ]; then
          kill $VNCPID
        fi
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
  

}
