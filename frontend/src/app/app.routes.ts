import { Routes } from '@angular/router';

// Page Components
import { HomeComponent } from './modules/pitchlink/pages/home/home.component';
import { PerfilComponent } from './modules/user/pages/perfil/perfil.component';
import { SwingComponent } from './modules/views/cards/pages/swing/swing.component';
import { LayoutComponent } from './modules/views/aplicacao/pages/layout/layout.component';
import { authGuardNotFoundGuard } from './core/guards/not-found/auth-guard-not-found.guard';
import { authGuardSuccessGuard } from './core/guards/success/auth-guard-success.guard';
import { IdeiaComponent } from './modules/user/pages/ideia/ideia.component';
import { MensagensComponent } from './modules/views/mensagens/mensagens.component';
import { SubscriptionComponent } from './modules/views/aplicacao/components/subscription/subscription.component';
import { PlanosComponent } from './modules/views/aplicacao/components/subscription/planos/planos.component';
import { SobreComponent } from './modules/pitchlink/pages/sobre/sobre.component';
import { ContatoComponent } from './modules/pitchlink/pages/contato/contato.component';
import { PoliticasPrivacidadeComponent } from './modules/pitchlink/pages/politicas-privacidade/politicas-privacidade.component';
import { LicenciamentoComponent } from './modules/pitchlink/pages/licenciamento/licenciamento.component';
import { TermosCondicoesComponent } from './modules/pitchlink/pages/termos-condicoes/termos-condicoes.component';
import { ListaIdeiasComponent } from './modules/views/aplicacao/components/lista-ideias/lista-ideias.component';

export const routes: Routes = [
    {
        path: '',
        component: HomeComponent,
    },
    {
        path: 'empresa',
        children: [
            {
                path: 'sobre',
                component: SobreComponent,
                title: 'Sobre Nós | PitchLink'
            },
            {
                path: 'contato',
                component: ContatoComponent,
                title: 'Contato | PitchLink'
            },
            {
                path: 'politicas',
                component: PoliticasPrivacidadeComponent,
                title: 'Políticas de Privacidade | PitchLink'
            },
            {
                path: 'licenciamento',
                component: LicenciamentoComponent,
                title: 'Licenciamento | PitchLink'
            },
            {
                path: 'termos',
                component: TermosCondicoesComponent,
                title: 'Termos e Condições | PitchLink'
            },
        ]
    },
    {
        path:'subscription', 
        component: SubscriptionComponent, 
        title: 'Minha assinatura | PitchLink',
    },
    {
        path:'subscription/:parametro', 
        component: PlanosComponent, 
        title: 'Planos | PitchLink',
    },
    {
        path: 'perfil',
        component: PerfilComponent,
        data: { hideNav: true },
        title: 'Meu Perfil | PitchLink'
    },
    {
        path: 'app',
        component: LayoutComponent,
        canActivate: [authGuardSuccessGuard],
        children: [
            {
                path:'recs', 
                component: SwingComponent
            },
            {
                path:'perfil', 
                component: PerfilComponent, 
                data: { hideNav: false },
                title: 'Meu Perfil | PitchLink'
            },
            {
                path:'mensagens', 
                component: MensagensComponent, 
                title: 'Mensagens | PitchLink'
            },
            {
                path:'listar_ideias', 
                component: ListaIdeiasComponent, 
                title: 'Lista de Ideias | PitchLink'
            },
            {
                path:'subscription', 
                component: SubscriptionComponent, 
                title: 'Minha assinatura | PitchLink',
            },
            {
                path:'subscription/:parametro', 
                component: PlanosComponent, 
                title: 'Mensagens | PitchLink',
            },
            { 
                path: 'ideia', 
                component: IdeiaComponent
            },
        ]
    },
        
    {
        path: '**',
        redirectTo: '',
        pathMatch: 'full'
    }
];
