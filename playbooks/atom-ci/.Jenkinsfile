pipeline {
agent {label "master" }

parameters {
    string(name: "ATOM_BRANCH", defaultValue: 'qa/2.x')
    string(name: "DEPLOYPUB_BRANCH", defaultValue: "dev/jenkins-ci")
    string(name: "SAMPLEDATA_BRANCH", defaultValue: "master")
    string(name: "JMETER_BRANCH", defaultValue: "main")
    string(name: "ANSIBLE_ATOM_BRANCH", defaultValue: "master")
    booleanParam(name: "PROVISION", defaultValue: "False")
    string(name: "SLAVE", defaultValue: "atom-ci")
}

stages {
  
    stage('Get code') {
    steps {
        script {
         //  Sanitize branch name
         // env.BRANCHNAME = sh(script: 'echo $ATOM_BRANCH | cut -d/ -f2 -', returnStdout: true).trim()
        // Set build name
         currentBuild.displayName = "#${BUILD_NUMBER} AtoM: ${ATOM_BRANCH}"
      currentBuild.description = "OS: atom-ci<br> Ansible role: ${ANSIBLE_ATOM_BRANCH}"
        }
      
      // Download code so jenkins can track it
      // TODO: clone archivematica in /opt/archivematica 
      git branch: env.ATOM_BRANCH, poll: false,
        url: 'https://github.com/artefactual/atom'
      }
    }

    
    
    stage('Deploy code'){
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
          userRemoteConfigs: [[url: 'https://github.com/artefactual/deploy-pub']]])
        checkout([$class: 'GitSCM',
        branches: [[name: env.ANSIBLE_ATOM_BRANCH]],
        doGenerateSubmoduleConfigurations: false,
        extensions:
          [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'ansible-atom']],
          submoduleCfg: [],
          userRemoteConfigs: [[url: 'https://github.com/artefactual-labs/ansible-atom']]])
    // Check if Archivematica is already installed (else, it's the first boot)   
    sh '''
       # Provision 
          cd deploy-pub/playbooks/atom-ci
          rm -rf roles/
          ansible-galaxy install -f -p roles -r requirements.yml
          rm -rf roles/artefactual.atom
          ln -s ${WORKSPACE}/ansible-atom roles/artefactual.atom
          
          export ANSIBLE_HOST_KEY_CHECKING=False
          ansible-playbook -i hosts \
          -e site=ci${BUILD_NUMBER} \
          -e atom_repository_version=${ATOM_BRANCH} \
          -e @template.yml \
          -e atom_flush_data=true \
          --tags=nginx,databases,users,atom-site atom26.yml
        
      '''

    }
    
    }

    stage('Unit tests') {
    agent {node {
        label "atom-ci"
        }
    }
    
    steps {
       
      sh '''
        # Recreate tests virtual environment
        cd /usr/share/nginx/ci${BUILD_NUMBER}/src/
        php symfony tools:get-version
        composer test -- --log-junit ${WORKSPACE}/results-${BUILD_NUMBER}.xml

        
      '''
      junit allowEmptyResults: false, healthScaleFactor: 10.0, keepLongStdio: true, testResults: 'results-${BUILD_NUMBER}.xml'

       }
    }
    
    
     stage('Load tests'){
     agent {node {
        label "master"
        }
    }
    steps {
        sh '''
        cd deploy-pub/playbooks/atom-ci
        ansible-playbook -i hosts \
           -e site=ci${BUILD_NUMBER} \
           -e @template.yml \
           load-demo-data.yml
        '''
        
        checkout([$class: 'GitSCM',
        branches: [[name: env.JMETER_BRANCH]],
        doGenerateSubmoduleConfigurations: false,
        extensions:
          [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'atom-jmeter-tests']],
          submoduleCfg: [],
          userRemoteConfigs: [[url: 'https://github.com/artefactual-labs/atom-jmeter-tests']]])
          
       sh '''
        cd atom-jmeter-tests/test/browsing/
        pwd
        export HEAP="-Xms1g -Xmx1g -XX:MaxMetaspaceSize=256m"
        export PATH=$PATH:/usr/local/jmeter/bin/
        jmeter -n -t browsing.jmx -Jserver=ci${BUILD_NUMBER}.pdt.accesstomemory.net -Jprotocol=http -l output/results-${BUILD_NUMBER}.csv
        pwd
        '''
        perfReport filterRegex: '', sourceDataFiles: 'atom-jmeter-tests/test/browsing/output/results-${BUILD_NUMBER}.csv'
    }
    }

    
    stage('Cleanup'){
     agent {node {
        label "master"
        }
    }
    steps {
        sh '''
        cd deploy-pub/playbooks/atom-ci
        ansible-playbook -i hosts \
           -e site=ci${BUILD_NUMBER} \
           decommission.yml
        '''
    
    }
    }
   
}


}
