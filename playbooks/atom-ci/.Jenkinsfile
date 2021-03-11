pipeline {
agent {label "master" }

parameters {
    string(name: "ATOM_BRANCH", defaultValue: 'qa/2.x')
    string(name: "DEPLOYPUB_BRANCH", defaultValue: "dev/jenkins-ci")
    string(name: "SAMPLEDATA_BRANCH", defaultValue: "master")
    string(name: "JMETER_BRANCH", defaultValue: "main")
    string(name: "ANSIBLE_ATOM_BRANCH", defaultValue: "master")
    booleanParam(name: "PROVISION", defaultValue: "True")
    booleanParam(name: "DECOMMISSION", defaultValue: "True")
    string(name: "SLAVE", defaultValue: "atom-ci")
}

stages {
  
    stage('Get code') {
    steps {
        script {
         //  Sanitize branch name
         env.BRANCHNAME = sh(script: 'echo $ATOM_BRANCH | cut -d\\/ -f2-  | sed -e "s/\\//-/g" -e "s/\\./-/g" | cut -c 1-16', returnStdout: true).trim()
        // Set build name
         currentBuild.displayName = "#${BUILD_NUMBER} AtoM: ${ATOM_BRANCH}"
      currentBuild.description = "OS: atom-ci<br> Ansible role: ${ANSIBLE_ATOM_BRANCH}<br> Site: ${BRANCHNAME}"
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
          -e site=${BRANCHNAME} \
          -e atom_repository_version=${ATOM_BRANCH} \
          -e @template.yml \
          -e atom_flush_data=true \
          --tags=acmetool,nginx,databases,users,atom-site,atom-sampledata atom.yml
        
      '''

    }
    
    }

   
    
     stage('Load tests'){
     agent {node {
        label "master"
        }
    }
    steps {
        
        checkout([$class: 'GitSCM',
        branches: [[name: env.JMETER_BRANCH]],
        doGenerateSubmoduleConfigurations: false,
        extensions:
          [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'atom-jmeter-tests']],
          submoduleCfg: [],
          userRemoteConfigs: [[url: 'https://github.com/artefactual-labs/atom-jmeter-tests']]])
          
       sh '''
        cd atom-jmeter-tests/test/browsing/
        export HEAP="-Xms1g -Xmx1g -XX:MaxMetaspaceSize=256m"
        export PATH=$PATH:/usr/local/jmeter/bin/
        rm -rf output/*
        jmeter -n -t browsing.jmx -Jserver=${BRANCHNAME}.pdt.accesstomemory.net -Jprotocol=http -l output/results.csv
        '''
        perfReport compareBuildPrevious: true,
                   filterRegex: '',
                   modeOfThreshold: true,
                   relativeFailedThresholdNegative: -5.0, relativeFailedThresholdPositive: -5.0,
                   relativeUnstableThresholdNegative: -1.0, relativeUnstableThresholdPositive: -1.0,
                   sourceDataFiles: 'atom-jmeter-tests/test/browsing/output/results.csv'
    }
    }

    
    stage('Cleanup'){
     agent {node {
        label "master"
        }
    }
    steps {
        sh '''
        if $DECOMMISSION; then
        cd deploy-pub/playbooks/atom-ci
        ansible-playbook -i hosts \
           -e site=${BRANCHNAME} \
           decommission.yml
        fi
        '''
    
    }
    }
   
}


}
