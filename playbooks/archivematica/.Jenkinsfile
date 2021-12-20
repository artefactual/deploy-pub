pipeline {
agent {label env.SLAVE }

parameters {
    string(name: "AM_REPO", defaultValue: 'https://github.com/artefactual/archivematica')
    string(name: "AM_BRANCH", defaultValue: 'qa/1.x')
    string(name: "AM_VERSION", defaultValue: "1.9")
    string(name: "SS_REPO", defaultValue: 'https://github.com/artefactual/archivematica-storage-service')
    string(name: "SS_BRANCH", defaultValue: "qa/0.x")
    string(name: "DEPLOYPUB_REPO", defaultValue: 'https://github.com/artefactual/deploy-pub')
    string(name: "DEPLOYPUB_BRANCH", defaultValue: "dev/jenkins-ci")
    string(name: "AMAUAT_REPO", defaultValue: 'https://github.com/artefactual-labs/archivematica-acceptance-tests')
    string(name: "AMAUAT_BRANCH", defaultValue: "qa/1.x")
    string(name: "SAMPLEDATA_BRANCH", defaultValue: "master")
    string(name: "ANSIBLE_ARCHIVEMATICA_REPO", defaultValue: 'https://github.com/artefactual-labs/ansible-archivematica-src')
    string(name: "ANSIBLE_ARCHIVEMATICA_BRANCH", defaultValue: "qa/1.x")
    string(name: "WEBDRIVER", defaultValue: "Firefox")
    string(name: "FEATURE", defaultValue: "virus.feature")
    booleanParam(name: "PROVISION", defaultValue: "False")
    string(name: "SLAVE", defaultValue: "ubuntu1804")
}

stages {
  
    stage('Get code') {
    steps {
        script {
         // Get slave ip and user 
          env.CLOUDVM = sh(script: 'echo $OPENSTACK_PUBLIC_IP', returnStdout: true).trim()
          env.CLOUDUSER = sh(script: 'echo $CLOUDUSER', returnStdout: true).trim()
          env.DEPLOY_TYPE = sh(script: 'echo ${DEPLOY_TYPE:-True}', returnStdout: true).trim()
          env.FIRSTBOOT = sh(script: 'if [ -d /var/archivematica/sharedDirectory ]; then echo false; else echo true;fi', returnStdout: true).trim()
        // Set build name
          currentBuild.displayName = "#${BUILD_NUMBER} AM: ${AM_BRANCH} SS: ${SS_BRANCH} (${CLOUDUSER})"
      currentBuild.description = "OS: ${SLAVE}<br> Feature: ${FEATURE} from ${AMAUAT_BRANCH}<br> Ansible role: ${ANSIBLE_ARCHIVEMATICA_BRANCH}"

        }
      
      // Download code so jenkins can track it
      // TODO: clone archivematica in /opt/archivematica 
      git branch: env.AM_BRANCH, poll: false,
        url: env.AM_REPO
      git branch: env.SS_BRANCH, poll: false,
        url: env.SS_REPO
      }
    }

    
    
    stage('Deploy vm'){
    agent {node {
        label "master"
        }
    }
    steps {
        sh '''mkdir -p $WORKSPACE'''
        // Clone deploypub and archivematica role
        checkout([$class: 'GitSCM',
        branches: [[name: env.DEPLOYPUB_BRANCH]],
        doGenerateSubmoduleConfigurations: false,
        extensions:
          [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'deploy-pub']],
          submoduleCfg: [],
          userRemoteConfigs: [[url: env.DEPLOYPUB_REPO]]])
        checkout([$class: 'GitSCM',
        branches: [[name: env.ANSIBLE_ARCHIVEMATICA_BRANCH]],
        doGenerateSubmoduleConfigurations: false,
        extensions:
          [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'ansible-archivematica-src']],
          submoduleCfg: [],
          userRemoteConfigs: [[url: env.ANSIBLE_ARCHIVEMATICA_REPO]]])
    // Check if Archivematica is already installed (else, it's the first boot)   
    sh '''
       if $FIRSTBOOT
         then
           TAGS="all"
         else
           TAGS="archivematica-src"
        fi
       # Provision 
       if $PROVISION || $FIRSTBOOT; then
          cd deploy-pub/playbooks/archivematica
          rm -rf roles/
          ansible-galaxy install -f -p roles -r requirements-qa.yml
          rm -rf roles/artefactual.archivematica-src
          ln -s ${WORKSPACE}/ansible-archivematica-src roles/artefactual.archivematica-src
          echo "am-local   ansible_host=${CLOUDVM}" > inventory
          cat inventory
          export ANSIBLE_HOST_KEY_CHECKING=False
          ansible-playbook -i inventory  \
          -e ansible_user=${CLOUDUSER} \
          -e archivematica_src_install_am=${DEPLOY_TYPE} \
          -e archivematica_src_install_ss=${DEPLOY_TYPE} \
          -e archivematica_src_install_devtools=False \
          -e archivematica_src_am_repo=${AM_REPO} \
          -e archivematica_src_am_version=${AM_BRANCH} \
          -e archivematica_src_ss_repo=${SS_REPO} \
          -e archivematica_src_ss_version=${SS_BRANCH} \
          -e archivematica_src_sample_data_version=${SAMPLEDATA_BRANCH} \
          -e archivematica_src_configure_am_api_key="HERE_GOES_THE_AM_API_KEY" \
          -e archivematica_src_configure_ss_api_key="HERE_GOES_THE_SS_API_KEY" \
          -e archivematica_src_reset_am_all=True \
          -e archivematica_src_reset_ss_db=True \
          --tags ${TAGS} singlenode.yml
 
        # Adapt sampledata paths for tests         
        ssh ${CLOUDUSER}@${CLOUDVM} "sudo usermod -a -G archivematica ${CLOUDUSER} || true"
        ssh ${CLOUDUSER}@${CLOUDVM} "sudo ln -sf /home/${CLOUDUSER} /home/archivematica"
        ssh ${CLOUDUSER}@${CLOUDVM} "sudo ln -sf /home/${CLOUDUSER}/archivematica-sampledata /home/"
       
        
        fi
      '''

    }
    
    }

    stage('Run tests') {
    agent {node {
        label "master"
        }
    }
    when {
        expression  { env.FEATURE != 'none' }
    }
    steps {
        git branch: env.AMAUAT_BRANCH, poll: false, url: env.AMAUAT_REPO

      sh '''
        # Recreate tests virtual environment
        rm -rf env
        virtualenv -p python3 env
        env/bin/pip install -r requirements.txt
        env/bin/pip install behave2cucumber

        # Launch vnc server
        VNCPID=123;
        until [ "x$VNCPID" == "x" ]
           do
           export DISPLAY=:$(($(( $RANDOM % 50 )) + 50 ))   
           VNCPID=$(ps aux | grep Xtig[h] | grep ${DISPLAY} | awk '{print $2}')
           done
           
        
         tightvncserver -geometry 1920x1080 ${DISPLAY}
          
        rm -rf results/${BUILD_NUMBER}
        mkdir -p results/${BUILD_NUMBER}
        echo "Using user ${CLOUDUSER}"
        echo "Running ${FEATURE}"
        for i in ${FEATURE}; do
          case "$i" in
            premis-events.feature) TIMEOUT=60m;;
            ingest-policy-check.feature) TIMEOUT=60m;;
            aip-encryption.feature) TIMEOUT=45m;;
            *) TIMEOUT=30m;;
          esac
          timeout $TIMEOUT env/bin/behave \
            -i $i \
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
            --junit --junit-directory=results/${BUILD_NUMBER}/ -v \
            -f=json -o=results/${BUILD_NUMBER}/output-$i.json \
            --no-skipped || true

          env/bin/python -m behave2cucumber -i results/${BUILD_NUMBER}/output-$i.json -o results/${BUILD_NUMBER}/cucumber-$i.json -r false || true
        done
      
        # Kill vnc server	
        VNCPID=$(ps aux | grep Xtig[h] | grep ${DISPLAY} | awk '{print $2}')
        if [ "x$VNCPID" != "x" ]; then	
          kill $VNCPID	
        fi
      '''
      junit allowEmptyResults: false, healthScaleFactor: 10.0, keepLongStdio: true, testResults: 'results/${BUILD_NUMBER}/*.xml'
      //fingerprint 'results/${BUILD_NUMBER}/*.xml'
      //archiveArtifacts 'results/${BUILD_NUMBER}/*.xml'
     // cucumber 'results/cucumber-*.json'
 
    }
    }

   
}
}
